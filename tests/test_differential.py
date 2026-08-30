"""Differential testing: two implementations, and whichever disagrees is wrong.

When a parser gets complicated enough that you cannot write down the expected
output by hand, write a second, dumber implementation and compare them. The
naive one is obviously correct and much too slow; the real one is fast and
subtle. Run both over a corpus and assert they agree.

This finds a class of bug nothing else does: the optimisation that is correct
on the fifteen specimens you wrote and wrong on the sixteenth. No assertion had
to be written per specimen, so the corpus can grow to thousands without anyone
maintaining expectations.

Two rules.

  1. The reference must be INDEPENDENT. If it shares helpers with the code
     under test, a bug in the shared part cancels out and the suite goes green
     against two identical mistakes. `_reference_walk` below re-derives the
     layout from the spec, using nothing from fwvault.parse.
  2. Disagreement is a failure, and the message must say which specimen. A
     differential test whose output is `assert False` is a differential test
     nobody can act on.

The oracle variant of this is the same idea with a trusted external tool as the
reference -- your parser against `readelf`, your decoder against ffmpeg. Same
shape, same rules, and the corpus is real files instead of generated ones.
"""

import struct

import pytest

from fwvault.errors import ParseError
from fwvault.parse import parse, walk_uf2
from fwvault.testing import NRF52840, RP2040, UNKNOWN_FAMILY, build_uf2


# ── the reference implementation ────────────────────────────────────────────

def _reference_walk(blob):
    """UF2, re-derived from the spec. Deliberately naive.

    Slices every field individually with its own struct.unpack rather than one
    packed format string, indexes rather than uses unpack_from, and rebuilds
    the whole list before returning anything. It is slower and clearer, and it
    shares no code with the implementation it checks -- which is the only
    property that makes it useful.
    """
    if len(blob) == 0 or len(blob) % 512 != 0:
        raise ParseError("not a whole number of blocks")

    out = []
    for i in range(len(blob) // 512):
        block = blob[i * 512:(i + 1) * 512]
        magic0 = struct.unpack("<I", block[0:4])[0]
        magic1 = struct.unpack("<I", block[4:8])[0]
        magic_end = struct.unpack("<I", block[508:512])[0]
        if magic0 != 0x0A324655 or magic1 != 0x9E5D5157:
            raise ParseError("block {}: start magic".format(i))
        if magic_end != 0x0AB16F30:
            raise ParseError("block {}: end magic".format(i))

        flags = struct.unpack("<I", block[8:12])[0]
        out.append({
            "index": i,
            "flags": flags,
            "target_addr": struct.unpack("<I", block[12:16])[0],
            "payload_size": struct.unpack("<I", block[16:20])[0],
            "block_no": struct.unpack("<I", block[20:24])[0],
            "num_blocks": struct.unpack("<I", block[24:28])[0],
            "family_id": struct.unpack("<I", block[28:32])[0] if flags & 0x2000 else None,
        })
    return out


def _as_dicts(blocks):
    return [
        {
            "index": b.index, "flags": b.flags, "target_addr": b.target_addr,
            "payload_size": b.payload_size, "block_no": b.block_no,
            "num_blocks": b.num_blocks, "family_id": b.family_id,
        }
        for b in blocks
    ]


# ── the corpus ──────────────────────────────────────────────────────────────

CORPUS = {
    "one-block": build_uf2(blocks=1),
    "many-blocks": build_uf2(blocks=17),
    "no-family": build_uf2(blocks=2, family=None, flags=0),
    "nrf52840": build_uf2(blocks=2, family=NRF52840),
    "unknown-family": build_uf2(blocks=2, family=UNKNOWN_FAMILY),
    "zero-payload": build_uf2(blocks=3, payload_size=0),
    "max-payload": build_uf2(blocks=3, payload_size=476),
    "oversized-payload": build_uf2(blocks=2, oversized_payload=5000),
    "shuffled": build_uf2(blocks=4, shuffle_block_no=True),
    "wrong-count": build_uf2(blocks=3, wrong_num_blocks=99),
    "backwards-addr": build_uf2(blocks=3, addr_step=-256, base_addr=0x10001000),
    "bad-end-magic": build_uf2(blocks=3, bad_end_magic=2),
    "bad-start-magic": build_uf2(blocks=2, bad_start_magic=1),
    "ragged": build_uf2(blocks=2) + b"\x00" * 3,
    "empty": b"",
}


@pytest.mark.parametrize("name", sorted(CORPUS), ids=sorted(CORPUS))
def test_the_walker_agrees_with_the_reference(name):
    """One test per specimen, named by specimen. Adding a corpus entry adds a
    test with no assertion to write, which is the whole economics of this
    technique.

    Both implementations are run under the same try, and BOTH outcomes are
    compared -- agreeing on the block list is not enough if one raises where
    the other does not."""
    blob = CORPUS[name]

    try:
        theirs = _reference_walk(blob)
        their_error = None
    except ParseError as exc:
        theirs, their_error = None, str(exc)

    try:
        ours = _as_dicts(walk_uf2(blob))
        our_error = None
    except ParseError as exc:
        ours, our_error = None, str(exc)

    assert (our_error is None) == (their_error is None), (
        "specimen {!r}: one implementation raised and the other did not "
        "(ours={!r}, reference={!r})".format(name, our_error, their_error)
    )
    if our_error is None:
        assert ours == theirs, "specimen {!r}: block streams differ".format(name)


def test_the_corpus_contains_both_outcomes():
    """The guard. A corpus where every specimen raises would make the test
    above pass trivially -- both implementations agree that everything is
    broken."""
    outcomes = set()
    for blob in CORPUS.values():
        try:
            _reference_walk(blob)
            outcomes.add("ok")
        except ParseError:
            outcomes.add("raised")
    assert outcomes == {"ok", "raised"}


def test_the_reference_shares_no_code_with_the_implementation():
    """Asserted structurally, because the value of a differential test is
    entirely in the independence of the two sides.

    Reads this file's own source and checks the reference function does not
    call into fwvault.parse. Crude, and it catches the refactor where someone
    'removes the duplication' between the two implementations and silently
    deletes the reason the test exists.
    """
    import inspect

    source = inspect.getsource(_reference_walk)
    for borrowed in ("UF2_MAGIC", "UF2_BLOCK_SIZE", "UF2_PAYLOAD_MAX",
                     "from fwvault", "parse.", "Block("):
        assert borrowed not in source, (
            "the reference implementation borrows {!r} from the code it is "
            "supposed to independently check".format(borrowed)
        )


# ── differential over generated input ───────────────────────────────────────

@pytest.mark.parametrize("blocks", range(1, 9))
@pytest.mark.parametrize("payload", [0, 1, 255, 476])
def test_agreement_across_a_generated_grid(blocks, payload):
    """32 specimens from two lines. The corpus above is hand-picked for
    interesting shapes; this is the boring sweep that covers the space between
    them, and it costs nothing to widen."""
    blob = build_uf2(blocks=blocks, payload_size=payload, family=RP2040)
    assert _as_dicts(walk_uf2(blob)) == _reference_walk(blob)


def test_the_folds_agree_on_payload_total():
    """Differential at a higher level: the reference computes the payload total
    the obvious way, `parse` accumulates it during the walk with a clamp. Two
    routes to one number."""
    blob = build_uf2(blocks=6, payload_size=300, family=RP2040)
    expected = sum(min(b["payload_size"], 476) for b in _reference_walk(blob))
    assert parse(blob).payload_bytes == expected
