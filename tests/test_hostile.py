"""Hostile input: truncation sweeps, bit flips, and deterministic fuzzing.

A parser's contract under bad input is narrow and absolute:

    for any byte string, parse() either returns an Image or raises ParseError.

Nothing else. Not IndexError, not struct.error, not MemoryError, not a hang.
Every one of those is the same defect wearing a different exception class, and
every one of them reaches a client as a 500 with a stack trace in it.

Three techniques here, in increasing order of how much they will annoy you:

    truncation sweep   every prefix of a valid file. Cheap, exhaustive, and it
                       finds more real bugs than the other two combined.
    bit flips          one byte changed at a time, walking the header.
    seeded fuzz        random garbage from a FIXED seed, so a failure is
                       reproducible from the test ID alone.

The seed is the part people get wrong. `random.randbytes(n)` with no seed gives
a suite that fails once a fortnight with no way to reproduce it, which trains
everyone to re-run CI until it goes green. A fixed seed gives a fixed corpus
that grows only when you decide it should.
"""

import random

import pytest

from fwvault.parse import parse
from fwvault.errors import ParseError
from fwvault.testing import build_elf, build_uf2

VALID = build_uf2(blocks=3)

# One list, used by the sweep AND by the meta-test that checks the sweep. Two
# copies of this drift the day someone edits one of them, and the meta-test
# then certifies a sweep nobody runs.
SWEEP = sorted(set(range(0, 1537, 64)) | {1, 7, 511, 513, 1535})


def _parses_or_raises_parse_error(blob):
    """The contract, as a callable. Returns the Image or None; lets ParseError
    through as success; re-raises everything else as the failure it is."""
    try:
        return parse(blob)
    except ParseError:
        return None


# ── truncation ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("length", SWEEP)
def test_every_truncation_is_survivable(length):
    """A prefix of a valid file is the most common corrupt file in the world:
    an interrupted upload.

    The step is 64 rather than 1 to keep the sweep at twenty-odd cases, and 64
    rather than 97 because 97 never lands on a multiple of 512. That version of
    this test looked thorough, ran twenty cases, and every single one of them
    took the same early `not a multiple of the block size` branch -- it never
    reached the walker at all. The meta-test below is what caught it.
    """
    _parses_or_raises_parse_error(VALID[:length])


def test_the_sweep_actually_covers_both_outcomes():
    """A sweep where every case raises proves nothing about the success path,
    and a sweep where every case passes is not testing truncation at all. This
    asserts the sweep straddles the boundary -- the meta-test that keeps the
    parametrize list honest when someone edits the step."""
    outcomes = {
        _parses_or_raises_parse_error(VALID[:n]) is not None for n in SWEEP
    }
    assert outcomes == {True, False}, (
        "every case in SWEEP had the same outcome, so the sweep is testing one "
        "branch twenty-five times"
    )


# ── single-byte mutation ────────────────────────────────────────────────────

@pytest.mark.parametrize("offset", [0, 3, 4, 7, 8, 12, 16, 20, 24, 28, 508, 511])
def test_header_byte_flips(offset):
    """Walk the header one field at a time. The offsets are the field
    boundaries from the UF2 spec, not arbitrary numbers -- a fuzzer that hits
    them by chance takes a million iterations to do what twelve named cases do
    immediately."""
    mutated = bytearray(VALID)
    mutated[offset] ^= 0xFF
    _parses_or_raises_parse_error(bytes(mutated))


def test_a_flip_in_the_payload_is_not_an_error():
    """The complement, and the one that catches an over-eager parser. Payload
    bytes are opaque; changing one must not change the verdict."""
    mutated = bytearray(VALID)
    mutated[100] ^= 0xFF
    assert parse(bytes(mutated)).block_count == 3


# ── seeded fuzz ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("seed", range(12))
def test_random_garbage_never_escapes_the_contract(seed):
    """Fixed seeds, so case 7 is the same twelve times out of twelve and a
    failure is reproducible by test ID with no artifact to attach.

    Growing the corpus means changing `range(12)`, which is a diff someone
    reviews, rather than waiting for a flake nobody can reproduce."""
    rng = random.Random(seed)
    blob = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 2048)))
    _parses_or_raises_parse_error(blob)


@pytest.mark.parametrize("seed", range(8))
def test_valid_prefix_random_tail(seed):
    """The interesting shape: enough valid structure to get past sniff, then
    garbage. Pure random bytes almost never reach the walker at all -- they
    fail the magic check in the first four bytes and prove nothing about the
    code past it. This is why unguided fuzzing of a parser with a magic number
    spends 99.9% of its budget on the same branch."""
    rng = random.Random(1000 + seed)
    tail = bytes(rng.randrange(256) for _ in range(512))
    _parses_or_raises_parse_error(VALID[:512] + tail)


# ── resource exhaustion ─────────────────────────────────────────────────────

def test_a_declared_block_count_does_not_allocate():
    """The classic parser DoS: a length field is trusted and pre-allocated. A
    two-block file claiming four billion blocks must cost two blocks of work.

    Asserted by wall-clock-free means -- the walker is driven to completion and
    the block count checked -- because a timing assertion on a loaded CI runner
    is a flake generator."""
    image = parse(build_uf2(blocks=2, wrong_num_blocks=0xFFFFFFFF))
    assert image.block_count == 2
    assert image.declared_blocks == 0xFFFFFFFF


def test_elf_entry_of_all_ones_is_data_not_an_address():
    """0xFFFFFFFFFFFFFFFF is a number the parser reports, not a pointer it
    follows. Obvious here, and exactly the assumption that turns a header
    parser into an exploit primitive when someone later adds a seek."""
    assert parse(build_elf(entry=0xFFFFFFFFFFFFFFFF)).entry == 0xFFFFFFFFFFFFFFFF


# ── the null hypothesis ─────────────────────────────────────────────────────

def test_hostile_specimens_do_not_all_look_alike():
    """A guard on this file itself.

    Every test above passes if `parse` is `def parse(b): raise ParseError("no")`.
    That is the failure mode of a hostile-input suite: it asserts only that
    nothing explodes, and something that refuses everything never explodes. So
    one test asserts the parser still says yes to the good specimen, and lives
    here rather than in test_parse.py so it is read next to what it guards.
    """
    assert parse(VALID).block_count == 3
