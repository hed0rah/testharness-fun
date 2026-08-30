"""Metamorphic testing: assertions that need no oracle.

Every technique so far needs someone to know the right answer. An example test
states it directly. A differential test borrows it from a second
implementation. A property test states a rule that implies it.

Metamorphic testing needs none of that. It relates two runs:

    if I change the input THIS way, the output must change THAT way

You never say what either output should be, only how they must relate. That
makes it the tool for the case the rest of the file cannot reach: no
specification, no reference implementation, and no way to state the answer.

It is also the technique that survives an AI author best, for the same reason
`test_oracle_independence.py` gives. A relation is a claim about the problem,
not about the code, so it cannot be transcribed from the implementation's
behaviour. Ask a model what `parse` returns for a given blob and it can read
the answer off the code. Ask it whether reordering blocks may change the
payload total and it has to reason about UF2.

The relations below are the useful shapes, in the order they are worth
learning:

    round trip      f(g(x)) == x                    the strongest, when g exists
    invariance      changing X must NOT change Y
    equivariance    changing X must change Y by a stated amount
    idempotence     doing it twice is doing it once
"""

import random

import pytest

from fwvault.errors import ParseError
from fwvault.parse import (
    UF2_BLOCK_SIZE,
    UF2_FLAG_FAMILY_ID,
    UF2_PAYLOAD_MAX,
    parse,
    serialize_uf2,
    walk_uf2,
)
from fwvault.testing import NRF52840, RP2040, build_uf2

SHAPES = {
    "plain": dict(blocks=3, family=RP2040),
    "single": dict(blocks=1, family=RP2040),
    "no-family": dict(blocks=2, family=None, flags=0),
    "other-family": dict(blocks=2, family=NRF52840),
    "zero-payload": dict(blocks=4, payload_size=0),
    "max-payload": dict(blocks=3, payload_size=UF2_PAYLOAD_MAX),
    "oversized": dict(blocks=2, oversized_payload=9999),
    "shuffled": dict(blocks=4, shuffle_block_no=True),
    "wrong-count": dict(blocks=3, wrong_num_blocks=99),
    "many": dict(blocks=17, family=RP2040),
}


def blocks_of(blob):
    return list(walk_uf2(blob))


# ── round trip ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("shape", sorted(SHAPES), ids=sorted(SHAPES))
def test_walk_then_serialize_is_the_identity(shape):
    """The strongest relation available, and the reason serialize_uf2 exists in
    the package rather than in this file.

    Byte for byte, not merely equivalent. Anything the walker drops on the
    floor shows up here as a diff, including fields nothing else in the suite
    looks at: the raw eighth word when the family flag is clear, and the
    payload bytes past `payload_size`.
    """
    blob = build_uf2(**SHAPES[shape])
    assert serialize_uf2(walk_uf2(blob)) == blob


@pytest.mark.parametrize("shape", sorted(SHAPES), ids=sorted(SHAPES))
def test_the_round_trip_is_idempotent(shape):
    """Doing it twice is doing it once. Cheap, and it catches a serializer that
    is only correct on the first pass, which is what you get if it mutates the
    blocks it was handed."""
    blob = build_uf2(**SHAPES[shape])
    once = serialize_uf2(walk_uf2(blob))
    twice = serialize_uf2(walk_uf2(once))
    assert once == twice == blob


def test_the_round_trip_test_can_fail():
    """A guard. `serialize_uf2` returning its input would pass every assertion
    above, so the relation is checked against a serializer that is wrong in one
    field.
    """
    blob = build_uf2(blocks=2, family=RP2040)
    from dataclasses import replace

    damaged = [replace(b, target_addr=b.target_addr + 1) for b in blocks_of(blob)]
    assert serialize_uf2(damaged) != blob


# ── invariance: what must NOT change ────────────────────────────────────────

@pytest.mark.parametrize("shape", sorted(SHAPES), ids=sorted(SHAPES))
def test_payload_contents_do_not_affect_the_header_reading(shape):
    """Rewriting every payload byte must not move a single field of the Image.

    Payload is opaque to a header parser. This is the relation that catches a
    parser reading a length or a flag out of the data area, which is a real
    class of bug and one an example-based test only finds if the example
    happens to contain the wrong byte.
    """
    from dataclasses import replace

    blob = build_uf2(**SHAPES[shape])
    rng = random.Random(0)
    scrambled = serialize_uf2(
        replace(b, data=bytes(rng.randrange(256) for _ in range(UF2_PAYLOAD_MAX)))
        for b in blocks_of(blob))

    assert parse(scrambled) == parse(blob)


@pytest.mark.parametrize("shape", sorted(SHAPES), ids=sorted(SHAPES))
def test_reordering_blocks_does_not_change_the_payload_total(shape):
    """Sum is commutative, so the total must be invariant under permutation
    even though blockNo warnings are not."""
    blob = build_uf2(**SHAPES[shape])
    blocks = blocks_of(blob)
    shuffled = list(blocks)
    random.Random(1).shuffle(shuffled)

    original = parse(blob)
    reordered = parse(serialize_uf2(shuffled))

    assert reordered.payload_bytes == original.payload_bytes
    assert reordered.block_count == original.block_count
    assert reordered.size == original.size


def test_the_family_flag_gates_the_family_reading():
    """Clearing one flag bit must change exactly one reading and nothing else.

    An equivalence relation stated across two runs, which is easier to be sure
    of than writing down what `family_id` should be for a given eighth word.
    """
    from dataclasses import replace

    blob = build_uf2(blocks=2, family=RP2040)
    with_flag = parse(blob)

    cleared = serialize_uf2(
        replace(b, flags=b.flags & ~UF2_FLAG_FAMILY_ID) for b in blocks_of(blob))
    without = parse(cleared)

    assert with_flag.family_id == RP2040 and with_flag.family == "RP2040"
    assert without.family_id is None and without.family is None
    assert without.payload_bytes == with_flag.payload_bytes
    assert without.block_count == with_flag.block_count


# ── equivariance: change the input, predict the change ──────────────────────

@pytest.mark.parametrize("extra", [1, 2, 5], ids=lambda n: "plus%d" % n)
def test_appending_blocks_moves_the_totals_by_a_stated_amount(extra):
    """Not "the total is 768" but "the total goes up by exactly this block's
    payload". The relation holds whatever the numbers happen to be, so it keeps
    holding when the specimen changes."""
    base = build_uf2(blocks=3, family=RP2040, payload_size=200)
    added = build_uf2(blocks=extra, family=RP2040, payload_size=200)

    before = parse(base)
    after = parse(serialize_uf2(blocks_of(base) + blocks_of(added)))

    assert after.block_count == before.block_count + extra
    assert after.payload_bytes == before.payload_bytes + 200 * extra
    assert after.size == before.size + UF2_BLOCK_SIZE * extra


@pytest.mark.parametrize("keep", [1, 2, 3], ids=lambda n: "first%d" % n)
def test_truncating_to_whole_blocks_is_predictable(keep):
    """Dropping trailing blocks removes exactly their contribution. Contrast
    tests/test_hostile.py, which truncates at arbitrary byte offsets and can
    only assert that nothing escapes the contract."""
    blob = build_uf2(blocks=4, family=RP2040, payload_size=100)
    kept = parse(serialize_uf2(blocks_of(blob)[:keep]))

    assert kept.block_count == keep
    assert kept.payload_bytes == 100 * keep
    assert kept.size == UF2_BLOCK_SIZE * keep


def test_clamping_is_monotonic_in_the_declared_size():
    """A relation over a whole family of inputs: raising payloadSize can never
    lower the reported total, and past the field width it stops moving.

    This states the clamp without naming 476, so the test does not have to
    agree with the implementation about where the ceiling is. It only has to be
    right that there is one.
    """
    from dataclasses import replace

    base = build_uf2(blocks=1, family=RP2040)
    totals = []
    for size in (0, 1, 100, 476, 477, 1000, 9999):
        blob = serialize_uf2(replace(b, payload_size=size) for b in blocks_of(base))
        totals.append(parse(blob).payload_bytes)

    assert totals == sorted(totals), "raising payloadSize lowered the total"
    assert totals[-1] == totals[-2] == totals[-3], "the clamp never engages"
    assert totals[0] == 0


# ── relations that must NOT hold ────────────────────────────────────────────

def test_corrupting_a_magic_number_is_not_invariant():
    """A guard on the whole file.

    Every relation above is satisfied by a parser that ignores its input and
    returns a constant. This one requires the parser to actually notice a
    change, so a constant parser fails here.
    """
    blob = build_uf2(blocks=3, family=RP2040)
    damaged = bytearray(serialize_uf2(blocks_of(blob)))
    damaged[UF2_BLOCK_SIZE + 508] ^= 0xFF        # block 1's end magic

    with pytest.raises(ParseError):
        parse(bytes(damaged))


def test_changing_payload_size_is_not_invariant():
    """The complement of the payload-contents relation. Changing the declared
    size MUST change the total, or the earlier invariance test is measuring a
    parser that reads nothing at all."""
    from dataclasses import replace

    base = build_uf2(blocks=2, family=RP2040, payload_size=100)
    bigger = serialize_uf2(replace(b, payload_size=200) for b in blocks_of(base))
    assert parse(bigger).payload_bytes != parse(base).payload_bytes


# ── generated, when hypothesis is available ─────────────────────────────────

def test_round_trip_over_generated_images():
    """The same relation, searched rather than enumerated.

    A metamorphic relation and a property-based generator are a natural pair:
    the relation says what must stay true, the generator finds the input that
    breaks it. Neither needs anyone to know the answer.
    """
    hypothesis = pytest.importorskip(
        "hypothesis", reason="generated round trip needs hypothesis; pip install -e .[test]")
    from hypothesis import given, settings
    from hypothesis import strategies as st

    @settings(deadline=None, max_examples=50)
    @given(
        blocks=st.integers(min_value=1, max_value=8),
        payload=st.integers(min_value=0, max_value=UF2_PAYLOAD_MAX),
        family=st.sampled_from([RP2040, NRF52840, None]),
    )
    def check(blocks, payload, family):
        blob = build_uf2(blocks=blocks, payload_size=payload, family=family,
                         flags=None if family else 0)
        assert serialize_uf2(walk_uf2(blob)) == blob
        assert parse(blob).payload_bytes == blocks * payload

    check()
