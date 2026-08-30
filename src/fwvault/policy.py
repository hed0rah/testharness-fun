"""Guardrails: the rules an artifact has to survive to be stored.

Two functions, and the split between them is the whole design.

    evaluate()  returns EVERY rejection that applies, in precedence order
    enforce()   raises the first one

`evaluate` returning a list rather than the first hit is what makes this
testable without combinatorial fixtures: one hostile artifact that trips four
rules produces four codes in one assertion, so a rule that silently stopped
firing cannot hide behind a rule that fires earlier. A first-hit-only design
gives you a green suite the day the OVERSIZE check breaks, because every
oversized specimen in the corpus also happens to be unsigned.

Codes are a public contract. Clients branch on `code`, never on `detail`, so
the codes are frozen and asserted in tests/test_contract.py while the wording
of `detail` is free to improve.
"""

from dataclasses import dataclass, field

from .errors import PolicyRejection
from .parse import UF2_FLAG_NOT_MAIN_FLASH

# Precedence. Order is behaviour: it decides which single code a client sees
# from enforce(), and it is asserted rather than left to dict ordering.
PRECEDENCE = (
    "MALFORMED",
    "OVERSIZE",
    "EMPTY_PAYLOAD",
    "UNKNOWN_FAMILY",
    "DENIED_MACHINE",
    "NOT_MAIN_FLASH",
    "REVOKED_KEY",
    "UNSIGNED",
    "TOO_MANY_WARNINGS",
)


@dataclass(frozen=True)
class Rejection:
    code: str
    detail: str


@dataclass(frozen=True)
class Policy:
    """Frozen so a test cannot mutate the shared default and leak into the next
    test. The fixture in conftest.py hands out copies via `replace()`."""

    max_bytes: int = 4 * 1024 * 1024
    min_payload_bytes: int = 1
    allowed_families: frozenset = frozenset(
        {0xE48BFF56, 0xE48BFF59, 0xADA52840}
    )
    allowed_machines: frozenset = frozenset({"ARM", "RISC-V"})
    require_signature: bool = True
    allow_unknown_family: bool = False
    max_warnings: int = 8
    deny_flags: int = UF2_FLAG_NOT_MAIN_FLASH
    denied_signers: frozenset = field(default_factory=frozenset)


DEFAULT = Policy()


def evaluate(image, verdict=None, policy=DEFAULT, flags=0):
    """Every rule that fires, in precedence order.

    `verdict` may be None, which means the signing oracle was never consulted.
    That is NOT the same as an unsigned artifact and does not produce UNSIGNED;
    the caller has to decide what to do about not knowing, and app.py answers
    503 rather than 422. See errors.py.
    """
    hits = {}

    if image.size > policy.max_bytes:
        hits["OVERSIZE"] = "{} bytes exceeds the {} byte ceiling".format(
            image.size, policy.max_bytes
        )
    if image.payload_bytes < policy.min_payload_bytes:
        hits["EMPTY_PAYLOAD"] = "carries {} payload bytes".format(image.payload_bytes)

    if image.kind == "uf2":
        if image.family_id is None:
            if not policy.allow_unknown_family:
                hits["UNKNOWN_FAMILY"] = "no family ID, or more than one"
        elif image.family_id not in policy.allowed_families:
            hits["UNKNOWN_FAMILY"] = "family {:#010x} is not on the allow list".format(
                image.family_id
            )
        if flags & policy.deny_flags:
            hits["NOT_MAIN_FLASH"] = "flags {:#010x} include a denied bit".format(flags)

    if image.kind == "elf" and image.machine not in policy.allowed_machines:
        hits["DENIED_MACHINE"] = "machine {} is not on the allow list".format(image.machine)

    if verdict is not None:
        if verdict.revoked:
            hits["REVOKED_KEY"] = "signed by revoked key {}".format(verdict.key_id)
        elif verdict.signer in policy.denied_signers:
            hits["REVOKED_KEY"] = "signer {} is denied".format(verdict.signer)
        elif policy.require_signature and not verdict.signed:
            hits["UNSIGNED"] = "no signature on record for this digest"

    if len(image.warnings) > policy.max_warnings:
        hits["TOO_MANY_WARNINGS"] = "{} parser warnings, ceiling is {}".format(
            len(image.warnings), policy.max_warnings
        )

    return tuple(Rejection(c, hits[c]) for c in PRECEDENCE if c in hits)


def enforce(image, verdict=None, policy=DEFAULT, flags=0):
    """Raise the highest-precedence rejection, or return cleanly."""
    hits = evaluate(image, verdict, policy, flags)
    if hits:
        raise PolicyRejection(hits[0].code, hits[0].detail)
