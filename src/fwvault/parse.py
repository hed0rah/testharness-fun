"""Header walkers for UF2 and ELF.

Two parsers, one shape: a generator that walks structure and yields records,
wrapped by a function that folds those records into an Image. Keeping the walk
separate from the fold is what makes the parser testable at two levels -- you
can assert on the tenth block of a 900-block file without materialising a
manifest, and you can test the fold with hand-built records and no bytes at
all.

The distinction that matters everywhere below: a malformed artifact raises, an
odd-but-survivable artifact records a warning and keeps going. Getting that
line wrong in either direction is a bug. Raise too eagerly and half of the real
world is unparseable; warn too eagerly and a corrupt image ships.
"""

import os
import struct
from dataclasses import dataclass, field

from .errors import ParseError, TruncatedError

# UF2, per the Microsoft spec. 512-byte blocks, three magic numbers, and 476
# usable payload bytes. The third magic at offset 508 is the point of the
# format: it makes a block self-identifying even when found mid-stream.
UF2_MAGIC0 = 0x0A324655          # "UF2\n"
UF2_MAGIC1 = 0x9E5D5157
UF2_MAGIC_END = 0x0AB16F30
UF2_BLOCK_SIZE = 512
UF2_PAYLOAD_MAX = 476

UF2_FLAG_NOT_MAIN_FLASH = 0x00000001
UF2_FLAG_FILE_CONTAINER = 0x00001000
UF2_FLAG_FAMILY_ID = 0x00002000
UF2_FLAG_MD5_PRESENT = 0x00004000
UF2_FLAG_EXT_TAGS = 0x00008000

ELF_MAGIC = b"\x7fELF"

# Family IDs we can name. An unknown family is not an error here -- naming is
# the parser's job only where it can be honest, and policy decides what is
# allowed. See policy.py: the two concerns are kept apart on purpose.
FAMILIES = {
    0xE48BFF56: "RP2040",
    0xE48BFF59: "RP2350-ARM-S",
    0xADA52840: "NRF52840",
    0x1C5F21B0: "ESP32-S3",
    0x68ED2B88: "SAMD51",
}

MACHINES = {0x28: "ARM", 0x3E: "x86-64", 0xF3: "RISC-V", 0x5E: "Xtensa"}


def _walker_raises():
    """In production an internal walker bug degrades to a warning so one bad
    block cannot take down an intake queue. In the suite it must be a loud
    traceback, or the suite's whole job -- noticing that the walker broke --
    is delegated to a log line nobody reads.

    tests/conftest.py sets this for every test. tests/test_walker.py turns it
    back off for exactly one test, to prove the production path still degrades.
    """
    return os.environ.get("FWVAULT_WALKER_RAISE") == "1"


@dataclass(frozen=True)
class Block:
    """One UF2 block, decoded. `offset` is absolute in the source buffer so a
    finding can always be pointed at with `xxd -s`."""

    index: int
    offset: int
    flags: int
    target_addr: int
    payload_size: int
    block_no: int
    num_blocks: int
    family_id: int | None
    # Present so a block can be written back out byte for byte. `family_id` is
    # the flag-gated reading; `raw_word8` is what is actually on the wire, which
    # is fileSize when the family flag is clear. serialize_uf2 needs the latter.
    raw_word8: int = 0
    data: bytes = b""


@dataclass(frozen=True)
class Image:
    """The fold. Everything downstream -- policy, storage, the API -- sees only
    this, which is why policy tests can construct one directly and never touch
    a byte of firmware."""

    kind: str
    size: int
    payload_bytes: int
    block_count: int
    declared_blocks: int | None = None
    family_id: int | None = None
    family: str | None = None
    entry: int | None = None
    machine: str | None = None
    warnings: tuple = field(default_factory=tuple)


def sniff(blob):
    """Identify by magic, never by filename.

    Returns "uf2" or "elf". Raises ParseError on anything else, including a
    buffer too short to hold a magic number -- which is a separate branch
    because an empty upload is the single most common hostile input and
    "index out of range" is not an answer to give a client.
    """
    if len(blob) < 8:
        raise TruncatedError(
            "buffer too short to identify", offset=0, needed=8, available=len(blob)
        )
    if blob[:4] == ELF_MAGIC:
        return "elf"
    if struct.unpack_from("<I", blob, 0)[0] == UF2_MAGIC0 and \
            struct.unpack_from("<I", blob, 4)[0] == UF2_MAGIC1:
        return "uf2"
    raise ParseError("unrecognised magic " + blob[:4].hex(), offset=0)


def walk_uf2(blob):
    """Yield every UF2 block in order. A generator, so a 40 MB image costs one
    block of memory and a caller can stop early.

    Structural faults raise. Everything survivable is the caller's problem to
    notice, which is what `parse_uf2` does with the block stream.
    """
    if not blob:
        raise TruncatedError("empty buffer", offset=0, needed=UF2_BLOCK_SIZE, available=0)
    if len(blob) % UF2_BLOCK_SIZE != 0:
        raise ParseError(
            "length {} is not a multiple of {}".format(len(blob), UF2_BLOCK_SIZE),
            offset=len(blob) - (len(blob) % UF2_BLOCK_SIZE),
        )

    for index in range(len(blob) // UF2_BLOCK_SIZE):
        off = index * UF2_BLOCK_SIZE
        m0, m1, flags, addr, size, no, total, fam = struct.unpack_from("<8I", blob, off)
        end = struct.unpack_from("<I", blob, off + 508)[0]

        if m0 != UF2_MAGIC0 or m1 != UF2_MAGIC1:
            raise ParseError("block {}: bad start magic".format(index), offset=off)
        if end != UF2_MAGIC_END:
            raise ParseError(
                "block {}: bad end magic {:#010x}".format(index, end), offset=off + 508
            )

        yield Block(
            index=index,
            offset=off,
            flags=flags,
            target_addr=addr,
            payload_size=size,
            block_no=no,
            num_blocks=total,
            family_id=fam if flags & UF2_FLAG_FAMILY_ID else None,
            raw_word8=fam,
            data=bytes(blob[off + 32:off + 508]),
        )


def serialize_uf2(blocks):
    """Blocks back to bytes. The inverse of walk_uf2.

    Exists so the parser can be tested without an oracle. For any valid image,
    `serialize_uf2(walk_uf2(b)) == b`, and that equality is checkable without
    anyone stating what the right answer is. See tests/test_metamorphic.py.

    Payload is padded or truncated to the 476-byte field, so a Block built by
    hand with a short `data` still produces a structurally valid image.
    """
    out = bytearray()
    for block in blocks:
        out += struct.pack(
            "<8I", UF2_MAGIC0, UF2_MAGIC1, block.flags, block.target_addr,
            block.payload_size, block.block_no, block.num_blocks, block.raw_word8,
        )
        payload = bytes(block.data[:UF2_PAYLOAD_MAX])
        out += payload + bytes(UF2_PAYLOAD_MAX - len(payload))
        out += struct.pack("<I", UF2_MAGIC_END)
    return bytes(out)


def parse_uf2(blob):
    """Fold a block stream into an Image, collecting anomalies as warnings."""
    warnings = []
    blocks = []
    try:
        for block in walk_uf2(blob):
            blocks.append(block)
    except ParseError:
        raise
    except Exception as exc:                      # noqa: BLE001 -- deliberate
        # A bug in the walker itself. In production this is one bad artifact,
        # not a dead queue; in the suite it is the traceback we came for.
        if _walker_raises():
            raise
        warnings.append("walker fault: " + type(exc).__name__)

    if not blocks:
        raise TruncatedError(
            "no blocks", offset=0, needed=UF2_BLOCK_SIZE, available=len(blob)
        )

    payload = 0
    declared = blocks[0].num_blocks
    families = set()
    prev_addr = None

    for block in blocks:
        if block.payload_size > UF2_PAYLOAD_MAX:
            warnings.append(
                "block {}: payloadSize {} exceeds {}, clamped".format(
                    block.index, block.payload_size, UF2_PAYLOAD_MAX
                )
            )
        payload += min(block.payload_size, UF2_PAYLOAD_MAX)

        if block.block_no != block.index:
            warnings.append(
                "block {}: blockNo says {}".format(block.index, block.block_no)
            )
        if block.num_blocks != declared:
            warnings.append(
                "block {}: numBlocks {} != {}".format(
                    block.index, block.num_blocks, declared
                )
            )
        if block.family_id is not None:
            families.add(block.family_id)
        if prev_addr is not None and block.target_addr < prev_addr:
            warnings.append("block {}: targetAddr goes backwards".format(block.index))
        prev_addr = block.target_addr

    if declared != len(blocks):
        warnings.append(
            "declares {} blocks, carries {}".format(declared, len(blocks))
        )
    if len(families) > 1:
        warnings.append("mixed family IDs: " + str(sorted(hex(f) for f in families)))

    family_id = next(iter(families)) if len(families) == 1 else None
    return Image(
        kind="uf2",
        size=len(blob),
        payload_bytes=payload,
        block_count=len(blocks),
        declared_blocks=declared,
        family_id=family_id,
        family=FAMILIES.get(family_id),
        entry=blocks[0].target_addr,
        warnings=tuple(warnings),
    )


def parse_elf(blob):
    """Enough ELF to answer the questions intake asks: 32 or 64 bit, what
    machine, where does it start. Not a linker."""
    if len(blob) < 24:
        raise TruncatedError(
            "ELF header truncated", offset=0, needed=24, available=len(blob)
        )
    ei_class, ei_data = blob[4], blob[5]
    if ei_class not in (1, 2):
        raise ParseError("bad EI_CLASS {}".format(ei_class), offset=4)
    if ei_data not in (1, 2):
        raise ParseError("bad EI_DATA {}".format(ei_data), offset=5)

    endian = "<" if ei_data == 1 else ">"
    wide = ei_class == 2
    warnings = []

    e_type, e_machine = struct.unpack_from(endian + "HH", blob, 16)
    need = 32 if wide else 28
    if len(blob) < need:
        raise TruncatedError(
            "ELF header truncated before e_entry", offset=24,
            needed=need, available=len(blob),
        )
    entry = struct.unpack_from(endian + ("Q" if wide else "I"), blob, 24)[0]

    if e_type not in (1, 2, 3, 4):
        warnings.append("unusual e_type {}".format(e_type))
    if entry == 0:
        warnings.append("entry point is 0")

    return Image(
        kind="elf",
        size=len(blob),
        payload_bytes=len(blob),
        block_count=1,
        entry=entry,
        machine=MACHINES.get(e_machine, "unknown({:#x})".format(e_machine)),
        warnings=tuple(warnings),
    )


def parse(blob):
    """Sniff, then dispatch. The only entry point the rest of the package uses."""
    kind = sniff(blob)
    return parse_uf2(blob) if kind == "uf2" else parse_elf(blob)
