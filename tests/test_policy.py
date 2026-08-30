"""Guardrails: proving a refusal happens, for the stated reason, and only then.

A policy test has three obligations and most suites discharge one.

  1. the rule fires on a violating artifact          (everyone does this)
  2. the rule does NOT fire on a compliant one       (half of everyone)
  3. the rule fires for the RIGHT REASON             (almost nobody)

Three is the one that rots. An oversized unsigned artifact is rejected by two
rules; a test that asserts "rejected" passes forever after the size check is
accidentally deleted, because the signature check is still there. That is why
`evaluate` returns every hit instead of the first, and why the assertions below
compare whole code sets rather than checking membership.

The last test in this file is the one that keeps the others honest: it asserts
that every code in PRECEDENCE has a test that produces it. A guardrail nobody
tests is a guardrail that stopped working at some point you cannot name.
"""

from dataclasses import replace

import pytest

from fwvault.parse import UF2_FLAG_NOT_MAIN_FLASH, parse
from fwvault.errors import PolicyRejection
from fwvault.policy import DEFAULT, PRECEDENCE, enforce, evaluate
from fwvault.signing import Verdict
from fwvault.testing import RP2040, UNKNOWN_FAMILY, build_elf, build_uf2

SIGNED = Verdict(signed=True, signer="ci-builder", key_id="k-2f81")
UNSIGNED = Verdict(signed=False)
REVOKED = Verdict(signed=True, signer="ci-builder", key_id="k-old", revoked=True)


def codes(*args, **kwargs):
    return [r.code for r in evaluate(*args, **kwargs)]


# ── the accepting case ──────────────────────────────────────────────────────

def test_a_compliant_artifact_is_accepted(policy):
    """First test in the file on purpose. If this one is missing, every
    rejection test below is satisfied by a policy that refuses everything."""
    image = parse(build_uf2(blocks=2, family=RP2040))
    assert codes(image, SIGNED, policy) == []


def test_enforce_returns_none_when_clean(policy):
    image = parse(build_uf2(blocks=2, family=RP2040))
    assert enforce(image, SIGNED, policy) is None


# ── one rule at a time ──────────────────────────────────────────────────────

def test_oversize(policy):
    tight = replace(policy, max_bytes=512)
    image = parse(build_uf2(blocks=2, family=RP2040))
    assert codes(image, SIGNED, tight) == ["OVERSIZE"]


def test_oversize_boundary_is_inclusive(policy):
    """max_bytes is a ceiling, not a limit you must stay under. Which one it is
    is a decision, and an untested boundary is a decision nobody made."""
    image = parse(build_uf2(blocks=2, family=RP2040))
    exact = replace(policy, max_bytes=image.size)
    assert codes(image, SIGNED, exact) == []
    assert codes(image, SIGNED, replace(policy, max_bytes=image.size - 1)) == ["OVERSIZE"]


def test_unknown_family(policy):
    image = parse(build_uf2(blocks=1, family=UNKNOWN_FAMILY))
    assert codes(image, SIGNED, policy) == ["UNKNOWN_FAMILY"]


def test_missing_family_id_is_also_unknown_family(policy):
    """A UF2 with the family flag clear carries no family at all. Absent and
    wrong are the same refusal here, and that is a deliberate choice worth a
    test of its own -- the two arrive by different code paths."""
    image = parse(build_uf2(blocks=1, family=None, flags=0))
    assert codes(image, SIGNED, policy) == ["UNKNOWN_FAMILY"]


def test_unknown_family_can_be_permitted(policy):
    lenient = replace(policy, allow_unknown_family=True)
    image = parse(build_uf2(blocks=1, family=None, flags=0))
    assert codes(image, SIGNED, lenient) == []


def test_unsigned(policy):
    image = parse(build_uf2(blocks=2, family=RP2040))
    assert codes(image, UNSIGNED, policy) == ["UNSIGNED"]


def test_revoked_key_outranks_unsigned(policy):
    """Revoked is a stronger statement than unsigned and must not be masked by
    it. `elif` ordering in policy.evaluate is what makes this true, which is
    exactly the kind of thing that survives a refactor only if tested."""
    image = parse(build_uf2(blocks=2, family=RP2040))
    assert codes(image, REVOKED, policy) == ["REVOKED_KEY"]


def test_denied_signer(policy):
    strict = replace(policy, denied_signers=frozenset({"laptop-build"}))
    image = parse(build_uf2(blocks=2, family=RP2040))
    verdict = Verdict(signed=True, signer="laptop-build", key_id="k-1")
    assert codes(image, verdict, strict) == ["REVOKED_KEY"]


def test_denied_machine(policy):
    image = parse(build_elf(machine=0x3E))       # x86-64, not on the list
    assert codes(image, SIGNED, policy) == ["DENIED_MACHINE"]


def test_not_main_flash_flag(policy):
    image = parse(build_uf2(blocks=2, family=RP2040))
    assert codes(image, SIGNED, policy, flags=UF2_FLAG_NOT_MAIN_FLASH) == \
        ["NOT_MAIN_FLASH"]


def test_empty_payload(policy):
    image = parse(build_uf2(blocks=1, family=RP2040, payload_size=0))
    assert codes(image, SIGNED, policy) == ["EMPTY_PAYLOAD"]


def test_too_many_warnings(policy):
    """A pile of individually-survivable anomalies is itself a signal. The
    specimen is built to trip several warnings at once rather than by faking an
    Image, so the count is the parser's real count."""
    image = parse(build_uf2(blocks=10, family=RP2040, shuffle_block_no=True))
    noisy = replace(policy, max_warnings=2)
    assert "TOO_MANY_WARNINGS" in codes(image, SIGNED, noisy)


# ── the interesting cases ───────────────────────────────────────────────────

def test_no_verdict_is_not_unsigned(policy):
    """The line the whole service is built around. `verdict=None` means we
    never asked, or asked and could not get an answer. It is not a signature
    check that came back negative, and it must not render as one.

    app.py turns this into 503, not 422. See test_asgi_raw.py.
    """
    image = parse(build_uf2(blocks=2, family=RP2040))
    assert "UNSIGNED" not in codes(image, None, policy)


def test_every_applicable_rule_fires_at_once(policy):
    """One artifact, four independent violations, four codes.

    This is the assertion a first-hit-only design cannot make, and it is the
    one that catches a rule quietly dying: if OVERSIZE stops firing, this list
    gets shorter and the test fails by name, rather than staying green because
    UNSIGNED still rejects the same file.
    """
    image = parse(build_uf2(blocks=2, family=UNKNOWN_FAMILY, payload_size=0))
    tight = replace(policy, max_bytes=100)
    assert codes(image, UNSIGNED, tight, flags=UF2_FLAG_NOT_MAIN_FLASH) == [
        "OVERSIZE", "EMPTY_PAYLOAD", "UNKNOWN_FAMILY", "NOT_MAIN_FLASH", "UNSIGNED",
    ]


def test_enforce_raises_the_highest_precedence_hit(policy):
    """Which single code a client sees is behaviour, not an implementation
    detail of dict ordering."""
    image = parse(build_uf2(blocks=2, family=UNKNOWN_FAMILY))
    with pytest.raises(PolicyRejection) as excinfo:
        enforce(image, UNSIGNED, replace(policy, max_bytes=100))
    assert excinfo.value.code == "OVERSIZE"


def test_precedence_order_is_stable(policy):
    """Rejections come back in PRECEDENCE order regardless of the order the
    rules happen to be evaluated in. Clients display the first one."""
    image = parse(build_uf2(blocks=2, family=UNKNOWN_FAMILY, payload_size=0))
    hits = codes(image, UNSIGNED, replace(policy, max_bytes=100))
    assert hits == sorted(hits, key=PRECEDENCE.index)


def test_the_default_policy_is_not_a_pushover():
    """DEFAULT is what runs in production when nobody passes anything. It gets
    its own test, because every other test in this file uses the `policy`
    fixture and would keep passing if DEFAULT were replaced with Policy(
    require_signature=False, allow_unknown_family=True)."""
    image = parse(build_uf2(blocks=1, family=UNKNOWN_FAMILY))
    assert set(codes(image, UNSIGNED, DEFAULT)) == {"UNKNOWN_FAMILY", "UNSIGNED"}


# ── the meta-test ───────────────────────────────────────────────────────────

def test_every_rejection_code_is_exercised_somewhere(request):
    """No code in PRECEDENCE may go untested.

    Implemented by running the suite's own specimens rather than by scraping
    source text, so it cannot be satisfied by a code appearing in a comment.
    When you add a rule, this fails until you add a case -- which is the only
    reliable way a guardrail suite stays complete as the policy grows.

    MALFORMED is the exception: it is raised by the parser before policy is
    ever consulted, so it appears in PRECEDENCE for ordering and is asserted in
    test_asgi_raw.py where it actually reaches a client.
    """
    seen = set()
    lenient = replace(DEFAULT, max_bytes=100, denied_signers=frozenset({"laptop-build"}))

    specimens = [
        (parse(build_uf2(blocks=2, family=UNKNOWN_FAMILY, payload_size=0)),
         UNSIGNED, lenient, UF2_FLAG_NOT_MAIN_FLASH),
        (parse(build_uf2(blocks=2, family=RP2040)), REVOKED, DEFAULT, 0),
        (parse(build_elf(machine=0x3E)), SIGNED, DEFAULT, 0),
        (parse(build_uf2(blocks=10, family=RP2040, shuffle_block_no=True)),
         SIGNED, replace(DEFAULT, max_warnings=2), 0),
    ]
    for image, verdict, pol, flags in specimens:
        seen.update(codes(image, verdict, pol, flags))

    untested = set(PRECEDENCE) - seen - {"MALFORMED"}
    assert not untested, (
        "these policy codes are never produced by any specimen in the suite, "
        "so nothing would notice if the rule stopped firing: " + ", ".join(sorted(untested))
    )
