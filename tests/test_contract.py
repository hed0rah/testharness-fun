"""Contract tests: the promises, asserted, so they cannot rot quietly.

A contract test does not check that code works. It checks that the SHAPE of
what you publish has not changed: the exported names, the status codes, the
exit codes, the rejection codes, the schema version, the route table.

Every one of those is something a consumer branches on, and every one of them
is invisible to a behavioural test. Rename a rejection code and the whole suite
stays green while every client's error handling silently stops matching.

This is also where the honest limit of a mocked suite gets paid for. Your fake
signing oracle encodes what you believe the real one does. When the real API
changes, the fake keeps agreeing with you. Nothing in this file can detect
that -- only a real request can, which is what the `net` test in
test_transport.py is for. What this file CAN do is pin your own side, so at
least the half you control does not drift unnoticed.
"""

import inspect
import json

import pytest

import fwvault
from fwvault import cli
from fwvault.app import create_app
from fwvault.policy import PRECEDENCE
from fwvault.store import SCHEMA_VERSION


# ── the public API ──────────────────────────────────────────────────────────

EXPECTED_API = {
    "Block", "DEFAULT", "FakeClock", "FwVaultError", "Image", "Manifest",
    "ParseError", "Policy", "PolicyRejection", "Rejection", "Response",
    "SCHEMA_VERSION", "SigningClient", "Store", "SystemClock", "TransportError",
    "TruncatedError", "VaultUnavailable", "Verdict", "__version__",
    "digest_of", "enforce", "evaluate", "parse", "parse_elf", "parse_uf2",
    "serialize_uf2", "sniff", "walk_uf2",
}


def test_the_public_api_is_exactly_what_is_documented():
    """Both directions matter. A name that disappeared breaks importers; a name
    that appeared is a promise nobody meant to make, and it is much harder to
    withdraw a year later."""
    assert set(fwvault.__all__) == EXPECTED_API


def test_every_exported_name_actually_exists():
    """`__all__` is just a list of strings. A typo in it produces an
    ImportError only for the person doing `from fwvault import *`, which may be
    nobody, for months."""
    missing = [name for name in fwvault.__all__ if not hasattr(fwvault, name)]
    assert missing == []


def test_no_public_name_starts_with_an_underscore():
    assert [n for n in fwvault.__all__ if n.startswith("_") and n != "__version__"] == []


def test_the_version_is_parseable():
    parts = fwvault.__version__.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)


# ── stable codes ────────────────────────────────────────────────────────────

def test_rejection_codes_are_frozen():
    """Clients branch on these strings. Renaming one is a breaking change
    whether or not anything else in the suite notices.

    `detail` is deliberately NOT pinned -- the wording should be free to
    improve, and a test that asserts on prose is a test that fails every time
    someone fixes a typo."""
    assert PRECEDENCE == (
        "MALFORMED", "OVERSIZE", "EMPTY_PAYLOAD", "UNKNOWN_FAMILY",
        "DENIED_MACHINE", "NOT_MAIN_FLASH", "REVOKED_KEY", "UNSIGNED",
        "TOO_MANY_WARNINGS",
    )


def test_exit_codes_are_frozen():
    """Build scripts branch on these. Renumbering one turns "rejected" into
    "infrastructure down" in somebody's CI, silently."""
    assert (cli.EXIT_OK, cli.EXIT_ERROR, cli.EXIT_USAGE, cli.EXIT_REJECTED,
            cli.EXIT_MALFORMED, cli.EXIT_UNAVAILABLE) == (0, 1, 2, 3, 4, 5)


def test_the_schema_version_is_an_integer_that_only_goes_up():
    """Pinned so bumping it is a deliberate edit to this line, next to the
    comment explaining why. A schema version that changes as a side effect of
    a refactor is worse than no schema version."""
    assert SCHEMA_VERSION == 3


def test_the_manifest_carries_its_schema_version(vault, uf2):
    """The version has to be ON the artifact, not just in the code. A reader
    five years from now has the file and not the source."""
    from fwvault.parse import parse
    from fwvault.store import Manifest, digest_of

    image = parse(uf2)
    digest, _created = vault.put(uf2, Manifest(
        digest=digest_of(uf2), kind=image.kind, size=image.size,
        family=image.family, entry=image.entry, signer=None, warnings=(),
    ))
    assert vault.manifest(digest)["schema_version"] == SCHEMA_VERSION


# ── the HTTP surface ────────────────────────────────────────────────────────

def test_the_route_table_is_what_is_documented(app):
    """Routes are a contract too. This asserts the table directly rather than
    by making requests, so a route that exists but is broken still shows up as
    a route."""
    table = {(method, pattern) for method, _regex, _handler, pattern in app.router.routes}
    assert table == {
        ("GET", "/healthz"),
        ("POST", "/artifact"),
        ("GET", "/vault/{digest}"),
    }


def test_every_response_is_json_with_a_content_length(app, uf2):
    """Two header promises, asserted once. A response with no content-length
    breaks keep-alive on some proxies, and it is exactly the sort of thing that
    works locally and fails behind a load balancer."""
    from test_asgi_raw import call

    for method, path, body in [("GET", "/healthz", b""),
                               ("POST", "/artifact", uf2),
                               ("GET", "/nope", b"")]:
        _status, headers, _payload = call(app, method, path, body)
        assert headers[b"content-type"] == b"application/json"
        assert b"content-length" in headers


def test_every_error_response_carries_an_error_code(app):
    """The shape of a failure is as much a contract as the shape of a success.
    A client cannot branch on a 422 whose body is a bare string one day and an
    object the next."""
    from test_asgi_raw import call
    from fwvault.testing import UNKNOWN_FAMILY, build_uf2

    cases = [
        ("GET", "/nope", b""),
        ("POST", "/artifact", b""),
        ("POST", "/artifact", b"\x00" * 64),
        ("POST", "/artifact", build_uf2(blocks=1, family=UNKNOWN_FAMILY)),
    ]
    for method, path, body in cases:
        status, _headers, payload = call(app, method, path, body)
        assert status >= 400
        assert isinstance(payload.get("error"), str), (method, path, payload)


# ── the fake's own contract ─────────────────────────────────────────────────

def test_the_shipped_doubles_match_the_transport_protocol():
    """The doubles in fwvault.testing are published for downstream users, so
    their signature is a contract. A fake whose signature drifts from the real
    transport passes every test in this repo and breaks in every consumer."""
    from fwvault.signing import UrllibTransport
    from fwvault.testing import RecordingTransport, ScriptedTransport

    real = inspect.signature(UrllibTransport.request)
    for double in (RecordingTransport, ScriptedTransport):
        assert inspect.signature(double.request) == real, double.__name__


def test_the_fake_and_the_real_transport_return_the_same_type():
    """Structural agreement, which is the most a mocked suite can assert about
    its own doubles without making a real request.

    Note what this canNOT tell you: whether the real signing oracle still
    answers in the shape `signed_body()` claims. Nothing in this process can.
    That gap is named in test_transport.py rather than papered over.
    """
    from fwvault.signing import Response
    from fwvault.testing import RecordingTransport, signed_body

    response = RecordingTransport(routes={"": Response(200, signed_body())}).request(
        "GET", "https://x/keys/abc"
    )
    assert isinstance(response, Response)
    assert set(response.json()) == {"signed", "signer", "key_id", "revoked"}


def test_the_json_the_fake_speaks_is_the_json_the_client_parses():
    """The fake's payload and the client's parser, checked against each other.
    Not proof the real API matches -- proof that OUR two halves do."""
    from fwvault.testing import signed_body

    payload = json.loads(signed_body().decode())
    from fwvault.signing import SigningClient

    source = inspect.getsource(SigningClient.verify)
    for key in payload:
        assert '"{}"'.format(key) in source or "'{}'".format(key) in source, (
            "the fake sends {!r} and verify() never reads it".format(key)
        )


# ── app construction ────────────────────────────────────────────────────────

def test_create_app_works_with_no_arguments(tmp_path, monkeypatch):
    """The production entry point. Every test in this suite passes
    collaborators explicitly, so nothing else would notice if the default
    construction path broke."""
    monkeypatch.chdir(tmp_path)
    app = create_app()
    assert callable(app)
    assert app.store is not None
