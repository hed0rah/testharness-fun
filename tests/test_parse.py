"""Parser tests: the assertion vocabulary, and what parametrize is for.

This is the file to read first. Everything else in the suite is a variation on
what happens here -- build a specimen, run one function, assert on a value.

Four things worth taking away:

  * `pytest.raises` with `match=` asserts the message too, and the message is
    what a user sees. A test that only asserts the type passes when the error
    says "None".
  * assert on the exception OBJECT, not just its class. TruncatedError carries
    offset/needed/available precisely so a test can say where.
  * parametrize with `ids=` so a failure names the case. "test_family[0-3]"
    tells you nothing; "test_family[nrf52840]" tells you everything.
  * one behaviour per test. A test with four unrelated asserts reports the
    first failure and hides the other three.
"""

import struct

import pytest

from fwvault.parse import (
    UF2_MAGIC0,
    UF2_MAGIC1,
    UF2_MAGIC_END,
    UF2_PAYLOAD_MAX,
    parse,
    sniff,
    walk_uf2,
)
from fwvault.errors import ParseError, TruncatedError
from fwvault.testing import NRF52840, RP2040, UNKNOWN_FAMILY, build_elf, build_uf2


# ── sniffing ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "blob,expected",
    [
        (build_uf2(blocks=1), "uf2"),
        (build_elf(), "elf"),
    ],
    ids=["uf2", "elf"],
)
def test_sniff_identifies_by_magic(blob, expected):
    assert sniff(blob) == expected


def test_sniff_ignores_the_filename():
    """The whole reason sniff takes bytes and not a path. A parser that trusts
    the extension is a parser that can be fooled by `mv evil.bin fw.uf2`."""
    assert sniff(build_elf()) == "elf"


@pytest.mark.parametrize("blob", [b"", b"\x00", b"\x7fEL", b"UF2"], ids=repr)
def test_short_buffers_are_truncated_not_garbage(blob):
    """`ids=repr` gives readable IDs for byte specimens without hand-writing
    them. The failure says test_short_buffers[b'\\x7fEL']."""
    with pytest.raises(TruncatedError) as excinfo:
        sniff(blob)
    assert excinfo.value.available == len(blob)
    assert excinfo.value.needed == 8


def test_unknown_magic_names_the_bytes_it_saw():
    """The message is part of the behaviour. A user pasting this into an issue
    should be able to tell what they uploaded."""
    with pytest.raises(ParseError, match=r"unrecognised magic deadbeef"):
        sniff(b"\xde\xad\xbe\xef" + b"\x00" * 8)


# ── the walker ──────────────────────────────────────────────────────────────

def test_walk_yields_one_block_per_512_bytes():
    blocks = list(walk_uf2(build_uf2(blocks=5)))
    assert [b.index for b in blocks] == [0, 1, 2, 3, 4]


def test_walk_is_lazy():
    """A generator, so a caller can stop. This matters for a 40 MB image and it
    is asserted rather than assumed, because turning `yield` into `return
    [...]` during a refactor is invisible to every other test in this file."""
    walker = walk_uf2(build_uf2(blocks=1000))
    first = next(walker)
    assert first.index == 0
    walker.close()


def test_block_offsets_are_absolute():
    """So a finding can be handed to `xxd -s`. Relative offsets are the reason
    people stop trusting parser output."""
    blocks = list(walk_uf2(build_uf2(blocks=3)))
    assert [b.offset for b in blocks] == [0, 512, 1024]


@pytest.mark.parametrize("bad_block", [0, 1, 2], ids=lambda n: "block%d" % n)
def test_bad_end_magic_is_located(bad_block):
    """Parametrizing over WHICH block is defective catches an off-by-one in the
    offset arithmetic that a single specimen would not."""
    blob = build_uf2(blocks=3, bad_end_magic=bad_block)
    with pytest.raises(ParseError) as excinfo:
        list(walk_uf2(blob))
    assert excinfo.value.offset == bad_block * 512 + 508


def test_length_not_a_multiple_of_the_block_size():
    blob = build_uf2(blocks=2) + b"\x00" * 7
    with pytest.raises(ParseError, match="not a multiple of 512"):
        list(walk_uf2(blob))


# ── the fold ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "family,expected",
    [
        (RP2040, "RP2040"),
        (NRF52840, "NRF52840"),
        (UNKNOWN_FAMILY, None),
    ],
    ids=["rp2040", "nrf52840", "unknown"],
)
def test_family_naming(family, expected):
    """An unknown family is None, not an exception. Naming is the parser's job
    only where it can be honest; deciding what is allowed is policy's job."""
    image = parse(build_uf2(blocks=1, family=family))
    assert image.family == expected
    assert image.family_id == family


def test_payload_bytes_sums_the_blocks():
    image = parse(build_uf2(blocks=4, payload_size=256))
    assert image.payload_bytes == 4 * 256


def test_oversized_payload_size_is_clamped_and_warned():
    """Two assertions, one behaviour: the clamp and the warning are the same
    decision seen from two sides, and a version that clamps silently is the bug
    this test exists to catch."""
    image = parse(build_uf2(blocks=2, oversized_payload=9999))
    assert image.payload_bytes == UF2_PAYLOAD_MAX + 256
    assert any("exceeds 476" in w for w in image.warnings)


def test_block_count_mismatch_is_a_warning_not_an_error():
    """The line this whole module is drawn around. A UF2 that says 9 blocks and
    carries 3 is odd, common, and readable. Raising here would make a large
    fraction of real firmware unparseable."""
    image = parse(build_uf2(blocks=3, wrong_num_blocks=9))
    assert image.block_count == 3
    assert any("declares 9 blocks, carries 3" in w for w in image.warnings)


def test_a_clean_image_warns_about_nothing():
    """The negative case, and the one people forget. Without it a parser that
    warns about everything passes every other test in this file."""
    assert parse(build_uf2(blocks=4)).warnings == ()


def test_out_of_order_block_numbers_are_reported_per_block():
    image = parse(build_uf2(blocks=3, shuffle_block_no=True))
    assert sum("blockNo says" in w for w in image.warnings) == 2


# ── ELF ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "machine,name",
    [(0x28, "ARM"), (0xF3, "RISC-V"), (0x5E, "Xtensa"), (0x99, "unknown(0x99)")],
    ids=["arm", "riscv", "xtensa", "unknown"],
)
def test_elf_machine_naming(machine, name):
    assert parse(build_elf(machine=machine)).machine == name


@pytest.mark.parametrize("bit64", [True, False], ids=["elf64", "elf32"])
@pytest.mark.parametrize("little", [True, False], ids=["le", "be"])
def test_elf_entry_across_class_and_endianness(bit64, little):
    """Stacked parametrize is a cartesian product: four tests from two lines.

    This is where the technique earns its keep -- the entry point is read at a
    different width AND a different byte order depending on two independent
    header fields, and all four combinations are real files somebody has."""
    image = parse(build_elf(entry=0x1234, bit64=bit64, little=little))
    assert image.entry == 0x1234


def test_elf_bad_class_is_located():
    blob = bytearray(build_elf())
    blob[4] = 7
    with pytest.raises(ParseError) as excinfo:
        parse(bytes(blob))
    assert excinfo.value.offset == 4


def test_elf_truncated_before_entry():
    with pytest.raises(TruncatedError) as excinfo:
        parse(build_elf(truncate_to=26))
    assert excinfo.value.needed == 32
    assert excinfo.value.available == 26


def test_zero_entry_point_is_a_warning():
    assert "entry point is 0" in parse(build_elf(entry=0)).warnings


# ── the specimen builder itself ─────────────────────────────────────────────

def test_the_builder_builds_what_it_claims():
    """A corpus generator is code, and untested code in a test corpus produces
    tests that pass against the wrong bytes. This asserts the raw layout
    directly, without going through the parser -- otherwise a matching pair of
    bugs in builder and parser cancels out and the suite stays green."""
    blob = build_uf2(blocks=1, family=RP2040, payload_size=128)
    assert len(blob) == 512
    assert struct.unpack_from("<I", blob, 0)[0] == UF2_MAGIC0
    assert struct.unpack_from("<I", blob, 4)[0] == UF2_MAGIC1
    assert struct.unpack_from("<I", blob, 16)[0] == 128
    assert struct.unpack_from("<I", blob, 28)[0] == RP2040
    assert struct.unpack_from("<I", blob, 508)[0] == UF2_MAGIC_END


# ── gaps a coverage report found ────────────────────────────────────────────
#
# Added after a branch-coverage pass. Each was a raise or a warning the suite
# never reached, which is what a coverage report is actually for: not a score,
# a list of places nothing looked.

def test_elf_bad_data_encoding_is_located():
    """EI_DATA at offset 5, the sibling of the EI_CLASS check above. The class
    branch had a test and the encoding branch did not."""
    blob = bytearray(build_elf())
    blob[5] = 9
    with pytest.raises(ParseError) as excinfo:
        parse(bytes(blob))
    assert excinfo.value.offset == 5


def test_elf_shorter_than_the_ident_block():
    """Under 24 bytes: too short even for e_type. Distinct from the truncation
    test above, which cuts between e_type and e_entry."""
    with pytest.raises(TruncatedError) as excinfo:
        parse(build_elf(truncate_to=20))
    assert excinfo.value.needed == 24
    assert excinfo.value.available == 20


@pytest.mark.parametrize("e_type", [0, 5, 99], ids=["none", "num", "high"])
def test_an_unusual_elf_type_is_a_warning_not_an_error(e_type):
    """e_type outside the four common values is odd, not fatal. The same
    raise-versus-warn line the UF2 walker draws."""
    image = parse(build_elf(e_type=e_type))
    assert any("unusual e_type" in w for w in image.warnings)
    assert image.kind == "elf"
