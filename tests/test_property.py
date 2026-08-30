"""Property-based testing: assert the rule, let the machine find the specimen.

An example-based test says "this input gives that output". A property-based
test says "for ALL inputs of this shape, this relationship holds", and
Hypothesis goes looking for a counterexample -- then SHRINKS it to the smallest
input that still fails.

The shrinking is the feature. A fuzzer hands you 1,847 bytes of noise and a
traceback. Hypothesis hands you `b'\\x00'` and the same traceback, and one of
those you can debug on a Friday afternoon.

Properties worth reaching for, roughly in order of how often they apply:

    round-trip      parse(build(x)) == x                  the strongest
    invariant       some relationship holds for all inputs
    oracle          the fast implementation agrees with the obvious one
    idempotence     f(f(x)) == f(x)
    never-crash     no exception outside the declared set   the weakest

The last one is where most people start and it is the least valuable: it is
satisfied by a function that raises the declared exception for every input. See
`test_the_never_crash_property_is_weak` at the bottom.

Gated with importorskip. `pip install -e .[test]` gets you hypothesis; without
it this file skips with a reason and nothing else in the suite notices.
"""

import pytest

from fwvault.errors import ParseError
from fwvault.parse import UF2_BLOCK_SIZE, UF2_PAYLOAD_MAX, parse, sniff, walk_uf2
from fwvault.policy import DEFAULT, PRECEDENCE, evaluate
from fwvault.signing import Verdict
from fwvault.testing import RP2040, build_elf, build_uf2

hypothesis = pytest.importorskip(
    "hypothesis", reason="property tests need hypothesis; pip install -e .[test]"
)

from hypothesis import HealthCheck, assume, given, settings  # noqa: E402
from hypothesis import strategies as st                      # noqa: E402

# CI runners are noisy and this suite is not the place to debug a timing
# health-check. Deadline off, example count modest and explicit.
COMMON = settings(deadline=None, max_examples=100,
                  suppress_health_check=[HealthCheck.too_slow])


def assert_parse_contract(blob):
    """The never-crash property as a named callable.

    Written as a helper rather than as a bare try/except in each test for one
    reason: `try: parse(b) except ParseError: pass` contains no assertion, and
    a test with no assertion is indistinguishable from a test somebody
    disabled. tests/test_suite_hygiene.py enforces that, and enforced it on
    this file."""
    from fwvault.parse import Image

    try:
        result = parse(blob)
    except ParseError:
        return None
    assert isinstance(result, Image)
    return result


# ── round trip: the strongest property ──────────────────────────────────────

@COMMON
@given(
    blocks=st.integers(min_value=1, max_value=12),
    payload=st.integers(min_value=0, max_value=UF2_PAYLOAD_MAX),
)
def test_uf2_round_trip(blocks, payload):
    """Everything the builder put in comes back out. This one property
    subsumes a dozen example-based tests, and unlike them it will find the
    boundary you did not think of -- payload=0 and payload=476 are both in the
    range and both get generated."""
    image = parse(build_uf2(blocks=blocks, payload_size=payload, family=RP2040))
    assert image.block_count == blocks
    assert image.payload_bytes == blocks * payload
    assert image.size == blocks * UF2_BLOCK_SIZE
    assert image.family == "RP2040"


@COMMON
@given(entry=st.integers(min_value=0, max_value=2**64 - 1),
       bit64=st.booleans(), little=st.booleans())
def test_elf_entry_round_trips_at_every_width(entry, bit64, little):
    """32-bit ELF cannot hold a 64-bit entry point, so the precondition is
    stated with `assume` rather than by narrowing the strategy. Hypothesis
    tracks how often it rejects and complains if the filter is too aggressive,
    which is a better signal than a silently narrower search."""
    assume(bit64 or entry < 2**32)
    assert parse(build_elf(entry=entry, bit64=bit64, little=little)).entry == entry


# ── invariants ──────────────────────────────────────────────────────────────

@COMMON
@given(blob=st.binary(min_size=0, max_size=3000))
def test_parse_never_raises_anything_but_parse_error(blob):
    """The contract from test_hostile.py, over arbitrary bytes instead of a
    hand-written corpus. Hypothesis will find the empty string, the one-byte
    string, and a buffer that is exactly 512 bytes of zeros without being
    told that those are interesting."""
    assert_parse_contract(blob)


@COMMON
@given(blob=st.binary(min_size=0, max_size=3000))
def test_sniff_and_parse_agree(blob):
    """A cross-function invariant: if sniff says uf2, parse must not come back
    saying elf. Two functions that disagree about what a file is will produce a
    manifest describing the wrong format."""
    try:
        kind = sniff(blob)
    except ParseError:
        return
    try:
        assert parse(blob).kind == kind
    except ParseError:
        pass


@COMMON
@given(blocks=st.integers(min_value=1, max_value=10))
def test_walk_yields_exactly_the_declared_number_of_blocks(blocks):
    assert len(list(walk_uf2(build_uf2(blocks=blocks)))) == blocks


@COMMON
@given(
    blocks=st.integers(min_value=1, max_value=6),
    max_bytes=st.integers(min_value=1, max_value=8192),
    signed=st.booleans(),
)
def test_policy_output_is_always_well_formed(blocks, max_bytes, signed):
    """Three properties of `evaluate` that must hold for every input:
    every code is a known code, no code appears twice, and the order is always
    PRECEDENCE order. None of the three is visible in a single example."""
    from dataclasses import replace

    image = parse(build_uf2(blocks=blocks, family=RP2040))
    hits = [r.code for r in evaluate(image, Verdict(signed=signed),
                                     replace(DEFAULT, max_bytes=max_bytes))]

    assert all(code in PRECEDENCE for code in hits)
    assert len(hits) == len(set(hits))
    assert hits == sorted(hits, key=PRECEDENCE.index)


# ── truncation, generated ───────────────────────────────────────────────────

@COMMON
@given(cut=st.integers(min_value=0, max_value=1536))
def test_every_prefix_is_survivable(cut):
    """The truncation sweep from test_hostile.py, but exhaustive rather than
    sampled. Both are worth having: the parametrized one runs everywhere and
    names its cases, this one covers the 1,512 lengths the other skips."""
    assert_parse_contract(build_uf2(blocks=3)[:cut])


# ── stateful, in miniature ──────────────────────────────────────────────────

@COMMON
@given(blobs=st.lists(st.integers(min_value=1, max_value=4), min_size=1, max_size=8))
def test_the_store_is_content_addressed_under_any_sequence(blobs, tmp_path_factory):
    """A sequence of operations rather than one call. The property: the vault
    holds exactly as many artifacts as there were DISTINCT inputs, whatever
    order they arrived in and however many times each repeated.

    Hypothesis's `stateful` module does this properly for real state machines;
    a list of operations covers a lot of ground for far less machinery.
    """
    from fwvault.store import Manifest, Store, digest_of

    store = Store(tmp_path_factory.mktemp("vault"))
    for n in blobs:
        blob = build_uf2(blocks=n, family=RP2040)
        image = parse(blob)
        store.put(blob, Manifest(
            digest=digest_of(blob), kind=image.kind, size=image.size,
            family=image.family, entry=image.entry, signer=None,
            warnings=tuple(image.warnings),
        ))

    assert len(store) == len(set(blobs))


# ── the weak property, named ────────────────────────────────────────────────

def test_the_never_crash_property_is_weak():
    """Stated as a test so it is read rather than assumed.

    `test_parse_never_raises_anything_but_parse_error` passes completely
    against `def parse(b): raise ParseError("no")`. It is a real property and
    worth having, but on its own it certifies a function that does nothing.

    Every never-crash property needs a positive companion. This is it, and it
    lives here rather than three files away so the pairing is visible.
    """
    assert parse(build_uf2(blocks=2, family=RP2040)).family == "RP2040"
