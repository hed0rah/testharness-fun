"""fwvault -- a firmware artifact intake service that exists to be tested.

It parses UF2 and ELF headers, asks a signing oracle about the digest, applies
policy, and stores what survives. Every one of those is a seam, and the seams
are the point: this package is the specimen under the microscope in the
testharness-fun deep dive, not a thing anyone should run.

`__all__` is the public API, and tests/test_contract.py asserts it. A name in
here is a promise; a name not in here can be renamed on a Tuesday.
"""

from .clock import FakeClock, SystemClock
from .errors import (
    FwVaultError,
    ParseError,
    PolicyRejection,
    TruncatedError,
    VaultUnavailable,
)
from .parse import (
    Block,
    Image,
    parse,
    parse_elf,
    parse_uf2,
    serialize_uf2,
    sniff,
    walk_uf2,
)
from .policy import DEFAULT, Policy, Rejection, enforce, evaluate
from .signing import Response, SigningClient, TransportError, Verdict
from .store import SCHEMA_VERSION, Manifest, Store, digest_of

__version__ = "0.3.0"

__all__ = [
    "Block",
    "DEFAULT",
    "FakeClock",
    "FwVaultError",
    "Image",
    "Manifest",
    "ParseError",
    "Policy",
    "PolicyRejection",
    "Rejection",
    "Response",
    "SCHEMA_VERSION",
    "SigningClient",
    "Store",
    "SystemClock",
    "TransportError",
    "TruncatedError",
    "VaultUnavailable",
    "Verdict",
    "__version__",
    "digest_of",
    "enforce",
    "evaluate",
    "parse",
    "parse_elf",
    "parse_uf2",
    "serialize_uf2",
    "sniff",
    "walk_uf2",
]
