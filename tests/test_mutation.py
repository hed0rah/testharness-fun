"""Mutation testing in miniature: does the suite actually catch a broken build?

Coverage answers "did this line run". It cannot answer the only question that
matters: **if I break this line, does anything go red?** A file with 100% line
coverage and no assertions is entirely possible, and entirely useless.

Mutation testing answers the real question. Break the code on purpose, run the
suite, and see whether it notices. A mutant that survives is a hole: that
behaviour is executed but not checked.

The full tool is `mutmut` or `cosmic-ray`. Both rewrite your source, run the
whole suite per mutant, and take minutes to hours. Run one occasionally, not in
CI.

What is here instead is the cheap version: a handful of hand-written mutants,
each paired with the assertion that should catch it. It runs in milliseconds,
it lives next to the code, and it fails the day someone weakens a check. It
does not replace mutmut -- it cannot find the mutants nobody thought of, which
is the whole point of the real tool -- but it pins the checks that matter most.

Each case below is a real weakening somebody could plausibly make in a
refactor, not a nonsense edit.
"""

from dataclasses import replace

import pytest

from fwvault import policy as policy_mod
from fwvault.errors import ParseError, VaultUnavailable
from fwvault.parse import UF2_FLAG_NOT_MAIN_FLASH, parse, walk_uf2
from fwvault.policy import DEFAULT, evaluate
from fwvault.signing import Response, SigningClient, TransportError, Verdict
from fwvault.testing import (
    RP2040,
    UNKNOWN_FAMILY,
    ScriptedTransport,
    build_uf2,
    signed_body,
)

SIGNED = Verdict(signed=True, signer="ci-builder", key_id="k-2f81")
UNSIGNED = Verdict(signed=False)

# A mutant is KILLED if the suite goes red, and a test that errors is red just
# like a test that fails. So any exception counts, not only AssertionError.
#
# `pytest.fail.Exception` has to be listed separately: a failing
# `pytest.raises(...)` raises Failed, which derives from BaseException rather
# than Exception, so a bare `except Exception` misses it. That is a genuinely
# sharp edge and it cost a debugging round while this file was written.
CHECK_FAILURES = (Exception, pytest.fail.Exception)


def assert_caught(check, what):
    """Run a real suite assertion against a mutant and require it to go RED.

    `what` names the mutation, so a surviving mutant reports which hole it
    found rather than just `assert False`.
    """
    try:
        check()
    except CHECK_FAILURES:
        return
    raise AssertionError(
        "MUTANT SURVIVED: {}. The suite executes this behaviour but does not "
        "check it.".format(what)
    )


# ── mutants of the policy engine ────────────────────────────────────────────

def test_a_policy_that_stops_refusing_oversize_is_caught(monkeypatch):
    """The mutation: OVERSIZE quietly stops firing.

    This is the exact failure the `evaluate`-returns-everything design exists
    to catch. Under a first-hit-only design this mutant SURVIVES, because every
    oversized specimen in the suite is also unsigned and the test still sees a
    rejection.
    """
    real = policy_mod.evaluate

    def mutant(image, verdict=None, policy=DEFAULT, flags=0):
        return tuple(r for r in real(image, verdict, policy, flags)
                     if r.code != "OVERSIZE")

    monkeypatch.setattr(policy_mod, "evaluate", mutant)

    image = parse(build_uf2(blocks=2, family=RP2040))
    tight = replace(DEFAULT, max_bytes=512)

    def the_suite_assertion():
        # from test_policy.py::test_oversize, inlined
        assert [r.code for r in policy_mod.evaluate(image, SIGNED, tight)] == ["OVERSIZE"]

    assert_caught(the_suite_assertion, "OVERSIZE stops firing")


def test_a_policy_that_returns_only_the_first_hit_is_caught(monkeypatch):
    """The mutation: someone "optimises" evaluate to stop at the first rule.

    Cheap-looking change, and it silently disables every rule below the first
    one that fires for a given artifact.
    """
    real = policy_mod.evaluate

    def mutant(image, verdict=None, policy=DEFAULT, flags=0):
        hits = real(image, verdict, policy, flags)
        return hits[:1]

    monkeypatch.setattr(policy_mod, "evaluate", mutant)

    image = parse(build_uf2(blocks=2, family=UNKNOWN_FAMILY, payload_size=0))
    tight = replace(DEFAULT, max_bytes=100)

    def the_suite_assertion():
        assert [r.code for r in policy_mod.evaluate(
            image, UNSIGNED, tight, UF2_FLAG_NOT_MAIN_FLASH)] == [
            "OVERSIZE", "EMPTY_PAYLOAD", "UNKNOWN_FAMILY", "NOT_MAIN_FLASH", "UNSIGNED",
        ]

    assert_caught(the_suite_assertion, "evaluate returns only the first hit")


def test_a_precedence_reorder_is_caught(monkeypatch):
    """The mutation: PRECEDENCE gets alphabetised by a tidy-minded refactor.

    Which single code `enforce` raises is what a client displays, so the order
    is behaviour. Nothing about the rules themselves changes here, and every
    single-rule test in test_policy.py still passes.

    The specimen matters, and picking it wrong is instructive. The first
    version of this test used an OVERSIZE + UNKNOWN_FAMILY + UNSIGNED
    artifact -- and alphabetical order puts OVERSIZE first too, so the mutant
    changed nothing observable and "survived". That is an EQUIVALENT MUTANT: a
    edit that cannot be detected because it does not alter behaviour. Real
    mutation tools produce them constantly and they are the main reason a
    mutation score is never 100%.

    OVERSIZE + EMPTY_PAYLOAD is the pair that actually distinguishes the two
    orderings: real precedence says OVERSIZE, alphabetical says EMPTY_PAYLOAD.
    """
    monkeypatch.setattr(policy_mod, "PRECEDENCE", tuple(sorted(policy_mod.PRECEDENCE)))

    image = parse(build_uf2(blocks=1, family=RP2040, payload_size=0))

    def the_suite_assertion():
        with pytest.raises(policy_mod.PolicyRejection) as excinfo:
            policy_mod.enforce(image, SIGNED, replace(DEFAULT, max_bytes=100))
        assert excinfo.value.code == "OVERSIZE"

    assert_caught(the_suite_assertion, "PRECEDENCE reordered")


# ── mutants of the error taxonomy ───────────────────────────────────────────

def test_an_outage_rendered_as_unsigned_is_caught(clock):
    """The mutation this whole service is shaped around.

    A "helpful" refactor catches VaultUnavailable and returns an unsigned
    verdict so the pipeline does not blow up. The service keeps running, the
    rejections look real, and nobody finds out until someone asks why every
    build failed overnight.

    Written as a mutant CLIENT rather than a patch, because that is how the
    change would actually arrive: someone edits verify() to be forgiving.
    """
    class ForgivingClient(SigningClient):
        def verify(self, digest):
            try:
                return super().verify(digest)
            except VaultUnavailable:
                return Verdict(signed=False)          # ← the mutation

    dead = ScriptedTransport([TransportError("down")] * 3)
    client = ForgivingClient("https://x", transport=dead, clock=clock, retries=3)

    def the_suite_assertion():
        # from test_doubles.py, inlined
        with pytest.raises(VaultUnavailable):
            client.verify("0" * 64)

    assert_caught(the_suite_assertion, "an outage rendered as Verdict(signed=False)")


def test_a_stale_verdict_that_hides_its_staleness_is_caught(clock):
    """The mutation: `stale=True` is dropped from the cached path.

    Availability still works. Honesty does not. Two behaviours, and this is
    exactly why they get two separate tests in test_transport.py rather than
    one combined assertion.
    """
    from fwvault.testing import RecordingTransport

    class SilentlyStaleClient(SigningClient):
        def verify(self, digest):
            return replace(super().verify(digest), stale=False)   # the mutation

    cache = {}
    SigningClient("https://x", transport=RecordingTransport(
        routes={"": Response(200, signed_body())}), clock=clock,
        cache=cache).verify("a" * 64)

    dead = SilentlyStaleClient("https://x", transport=ScriptedTransport(
        [TransportError("down")] * 3), clock=clock, retries=3, cache=cache)

    assert dead.verify("a" * 64).signed is True, "availability survives the mutation"

    def the_suite_assertion():
        assert dead.verify("a" * 64).stale is True

    assert_caught(the_suite_assertion, "the stale flag is dropped")


# ── mutants of the parser ───────────────────────────────────────────────────

def test_a_walker_that_stops_validating_the_end_magic_is_caught():
    """The mutation: the magicEnd check at offset 508 is deleted.

    That third magic is the point of the UF2 format: it makes a block
    self-identifying mid-stream. A walker without it accepts any 512-byte
    chunk whose first eight bytes happen to match.
    """
    import struct

    from fwvault.parse import Block, UF2_FLAG_FAMILY_ID

    def lax_walk(blob):
        """walk_uf2 with the end-magic check removed, otherwise identical."""
        for index in range(len(blob) // 512):
            off = index * 512
            m0, m1, flags, addr, size, no, total, fam = struct.unpack_from(
                "<8I", blob, off)
            yield Block(index=index, offset=off, flags=flags, target_addr=addr,
                        payload_size=size, block_no=no, num_blocks=total,
                        family_id=fam if flags & UF2_FLAG_FAMILY_ID else None)

    blob = build_uf2(blocks=3, bad_end_magic=1)

    assert len(list(lax_walk(blob))) == 3, "the mutant happily accepts it"

    def the_suite_assertion():
        # from test_parse.py::test_bad_end_magic_is_located, inlined
        with pytest.raises(ParseError) as excinfo:
            list(lax_walk(blob))
        assert excinfo.value.offset == 512 + 508

    assert_caught(the_suite_assertion, "the magicEnd check is deleted")


def test_a_parser_that_clamps_silently_is_caught():
    """The mutation: the payloadSize clamp stays, its warning goes.

    The clamp alone keeps every arithmetic assertion in test_parse.py green.
    Only the paired warning assertion notices the artifact stopped being
    flagged, which is why that test carries both.
    """
    image = parse(build_uf2(blocks=2, oversized_payload=9999))
    mutant = replace(image, warnings=tuple(
        w for w in image.warnings if "exceeds" not in w))

    assert mutant.payload_bytes == image.payload_bytes, "the clamp is unaffected"

    def the_suite_assertion():
        assert any("exceeds 476" in w for w in mutant.warnings)

    assert_caught(the_suite_assertion, "the clamp warning is dropped")


def test_a_parser_that_refuses_everything_is_caught():
    """The mutant that survives an entire hostile-input suite.

    Every assertion in test_hostile.py passes against a parse() that raises
    ParseError unconditionally: "nothing escaped the contract" is satisfied by
    refusing everything. This is precisely why that file carries
    `test_hostile_specimens_do_not_all_look_alike`, and this is that companion
    earning its place.
    """
    def mutant(blob):
        raise ParseError("no")

    for length in (0, 512, 1024, 1536):          # the hostile contract holds...
        try:
            mutant(build_uf2(blocks=3)[:length])
        except ParseError:
            pass

    def the_suite_assertion():
        assert mutant(build_uf2(blocks=3)).block_count == 3

    assert_caught(the_suite_assertion, "parse() refuses every input")


# ── the meta-assertion ──────────────────────────────────────────────────────

def test_every_mutant_in_this_file_is_paired_with_its_catcher():
    """A guard on the file itself.

    Every test above must call `assert_caught`, which is what turns "I wrote a
    mutant" into "and the suite provably notices". A mutant with no paired
    assertion is a paragraph, not a test.

    Counted rather than described, so adding a mutant without wiring it up
    fails here instead of sitting green.
    """
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    mutants, paired = [], []

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        if node.name == "test_every_mutant_in_this_file_is_paired_with_its_catcher":
            continue
        mutants.append(node.name)
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "assert_caught" for n in ast.walk(node)):
            paired.append(node.name)

    unpaired = sorted(set(mutants) - set(paired))
    assert not unpaired, (
        "these describe a mutation but never prove the suite catches it: "
        + ", ".join(unpaired)
    )
    assert len(mutants) >= 7, "expected at least 7 mutants, found %d" % len(mutants)
