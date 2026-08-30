"""The error taxonomy, which is the whole design.

Three kinds of bad thing happen in an intake service, and conflating any two of
them is how a service starts lying about its inputs:

    ParseError       the blob is malformed. A fact about the artifact.
    PolicyRejection  the blob parsed fine and we refuse it anyway. A decision.
    VaultUnavailable we could not tell. A fact about US, never about the blob.

The third is the one that gets swallowed. A signing oracle that times out and
is reported as "unsigned" turns an outage into a stream of confident refusals,
and the refusals look exactly like the real ones. So VaultUnavailable is not a
subclass of PolicyRejection and never converts into one.
"""


class FwVaultError(Exception):
    """Base for everything this package raises on purpose."""


class ParseError(FwVaultError):
    """The bytes are not what they claim to be."""

    def __init__(self, message, offset=None):
        super().__init__(message)
        self.offset = offset


class TruncatedError(ParseError):
    """Ran off the end of the buffer. Its own class because a truncated file is
    a routine, expected input and the caller usually wants to say so."""

    def __init__(self, message, offset=None, needed=None, available=None):
        super().__init__(message, offset=offset)
        self.needed = needed
        self.available = available


class PolicyRejection(FwVaultError):
    """A refusal, with a stable machine-readable code.

    `code` is part of the public contract -- clients branch on it -- so it is
    asserted in tests/test_contract.py rather than left to drift with the
    wording of `detail`.
    """

    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class VaultUnavailable(FwVaultError):
    """We could not reach something we needed. Never a statement about the
    artifact, and never rendered as a rejection."""
