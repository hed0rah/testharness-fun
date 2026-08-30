"""Driving an ASGI app with no test client at all.

Twenty lines of harness, no dependencies, and it does everything a test client
does: build a scope, feed a receive, collect the sends. Read `call` below and
the phrase "ASGI test client" stops being magic.

Why bother, when httpx.ASGITransport exists and the next file uses it?

  * it is the only way to send things a real client will not let you send: a
    body in three chunks, a disconnect mid-stream, a scope with a header a
    client library would normalise away
  * it makes the lifespan protocol visible, which is where hangs come from
  * when a framework test client behaves strangely, this is how you find out
    whether the app or the client is wrong

The assertions in this file and in test_asgi_httpx.py are deliberately near
identical. That is the demonstration: if swapping the client changes what you
assert, you were testing the client.
"""

import json

import pytest

from fwvault.app import create_app
from fwvault.errors import VaultUnavailable
from fwvault.parse import UF2_FLAG_NOT_MAIN_FLASH
from fwvault.testing import UNKNOWN_FAMILY, build_elf, build_uf2

import asyncio


# ── the harness ─────────────────────────────────────────────────────────────

def call(app, method="GET", path="/", body=b"", headers=None, chunks=None):
    """One request, start to finish. Returns (status, headers, parsed body).

    `chunks` overrides `body` and delivers it as several http.request messages
    with more_body=True, which is how you exercise a streaming read. No HTTP
    client will hand you that control.
    """
    incoming = list(chunks) if chunks is not None else [body]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": ("127.0.0.1", 51234),
        "server": ("testserver", 80),
        "scheme": "http",
    }

    async def receive():
        if incoming:
            part = incoming.pop(0)
            return {"type": "http.request", "body": part, "more_body": bool(incoming)}
        return {"type": "http.disconnect"}

    sent = []

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))

    start = next(m for m in sent if m["type"] == "http.response.start")
    payload = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), json.loads(payload)


def lifespan(app):
    """Startup and shutdown, driven by hand. A test client does this for you,
    silently, and hangs forever if the app never answers -- which is why the
    app answers, and why this exists to prove it."""
    events = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    sent = []

    async def receive():
        return events.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send))
    return [m["type"] for m in sent]


# ── routing ─────────────────────────────────────────────────────────────────

def test_healthz(app):
    status, _headers, body = call(app, "GET", "/healthz")
    assert status == 200
    assert body["ok"] is True


def test_unknown_path_is_404(app):
    status, _headers, body = call(app, "GET", "/nope")
    assert status == 404
    assert body["error"] == "NOT_FOUND"


def test_wrong_method_is_405_not_404(app):
    """The distinction matters to a client. A POST to a GET-only route that
    answers 404 sends the caller looking for a path that is right there."""
    status, _headers, body = call(app, "POST", "/healthz")
    assert status == 405
    assert body["error"] == "METHOD_NOT_ALLOWED"


def test_route_patterns_are_anchored(app):
    """`/vault/{digest}` must not match `/vault/abc/extra`. An unanchored
    router is a routing bug wearing a security bug's clothes -- it is how a
    path parameter starts swallowing path segments."""
    status, _headers, _body = call(app, "GET", "/vault/" + "a" * 64 + "/extra")
    assert status == 404


def test_lifespan_completes(app):
    """Both events answered. An app that ignores lifespan hangs a test client
    at import time, and that failure looks like the test framework being
    broken rather than the app."""
    assert lifespan(app) == ["lifespan.startup.complete", "lifespan.shutdown.complete"]


# ── the ingest pipeline, end to end ─────────────────────────────────────────

def test_a_good_artifact_is_stored(app, uf2):
    status, _headers, body = call(app, "POST", "/artifact", uf2)
    assert status == 201
    assert body["created"] is True
    assert app.store.has(body["digest"])


def test_the_same_bytes_twice_is_not_a_new_artifact(app, uf2):
    """Content addressing, observable from outside: second POST answers 200
    with created=false, and the vault still holds one artifact."""
    call(app, "POST", "/artifact", uf2)
    status, _headers, body = call(app, "POST", "/artifact", uf2)
    assert (status, body["created"]) == (200, False)
    assert len(app.store) == 1


def test_the_manifest_round_trips(app, uf2):
    _status, _headers, posted = call(app, "POST", "/artifact", uf2)
    status, _headers, manifest = call(app, "GET", "/vault/" + posted["digest"])
    assert status == 200
    assert manifest["family"] == "RP2040"
    assert manifest["signer"] == "ci-builder"


def test_an_absent_digest_is_404(app):
    status, _headers, _body = call(app, "GET", "/vault/" + "f" * 64)
    assert status == 404


def test_a_malformed_digest_is_400_not_404(app):
    """400 says "that is not a digest"; 404 says "no such artifact". A client
    retrying a typo forever is the cost of conflating them."""
    status, _headers, body = call(app, "GET", "/vault/not-a-digest")
    assert status == 400
    assert body["error"] == "BAD_DIGEST"


# ── the error taxonomy, as status codes ─────────────────────────────────────

def test_malformed_bytes_are_422_with_an_offset(app):
    """A fact about the artifact: deterministic, client-fixable, and it names
    the byte."""
    status, _headers, body = call(app, "POST", "/artifact", build_uf2(blocks=2, bad_end_magic=1))
    assert status == 422
    assert body["error"] == "MALFORMED"
    assert body["offset"] == 512 + 508


def test_a_policy_rejection_is_422_with_its_code(app):
    status, _headers, body = call(
        app, "POST", "/artifact", build_uf2(blocks=1, family=UNKNOWN_FAMILY)
    )
    assert status == 422
    assert body["error"] == "UNKNOWN_FAMILY"


def test_a_denied_flag_header_reaches_policy(app, uf2):
    status, _headers, body = call(
        app, "POST", "/artifact", uf2,
        headers={"x-fwvault-flags": hex(UF2_FLAG_NOT_MAIN_FLASH)},
    )
    assert (status, body["error"]) == (422, "NOT_MAIN_FLASH")


def test_a_junk_header_is_400_not_a_500(app, uf2):
    status, _headers, body = call(
        app, "POST", "/artifact", uf2, headers={"x-fwvault-flags": "banana"}
    )
    assert (status, body["error"]) == (400, "BAD_HEADER")


def test_an_oracle_outage_is_503_and_never_a_rejection(vault, policy, uf2, clock):
    """The headline assertion of the whole service.

    The oracle is down. The artifact is perfectly good. The answer is 503 with
    a Retry-After, NOT 422 UNSIGNED -- because we do not know, and saying
    "unsigned" would be a statement about the artifact that we are not entitled
    to make. See errors.py.
    """
    class DeadClient:
        def verify(self, digest):
            raise VaultUnavailable("oracle down")

    app = create_app(store=vault, client=DeadClient(), policy=policy)
    status, headers, body = call(app, "POST", "/artifact", uf2)

    assert status == 503
    assert body["error"] == "ORACLE_UNAVAILABLE"
    assert headers[b"retry-after"] == b"5"
    assert len(vault) == 0, "nothing is stored when we could not verify it"


def test_an_empty_body_is_400(app):
    status, _headers, body = call(app, "POST", "/artifact", b"")
    assert (status, body["error"]) == (400, "EMPTY_BODY")


# ── things only the raw harness can do ──────────────────────────────────────

def test_a_chunked_body_is_reassembled(app, uf2):
    """Three http.request messages, one artifact. No HTTP client will let you
    choose the chunk boundaries, and the reassembly loop is exactly where an
    off-by-one costs you a corrupted upload."""
    chunks = [uf2[:100], uf2[100:700], uf2[700:]]
    status, _headers, _body = call(app, "POST", "/artifact", chunks=chunks)
    assert status == 201


def test_oversize_is_refused_before_the_whole_body_is_buffered(vault, client, policy):
    """413 while the body is still arriving. The point is the ordering: a
    service that buffers 900 MB and THEN checks the limit has no limit.

    Only reachable because the harness controls the chunking."""
    app = create_app(store=vault, client=client, policy=policy, max_body=1024)
    big = build_uf2(blocks=8)
    status, _headers, body = call(app, "POST", "/artifact", chunks=[big[i:i + 512]
                                                                    for i in range(0, len(big), 512)])
    assert (status, body["error"]) == (413, "OVERSIZE")
    assert len(vault) == 0


def test_a_disconnect_mid_body_produces_no_response(app, uf2):
    """A client that hangs up. The app must not send a response to a closed
    connection, and must not raise. Genuinely unreachable through a normal
    test client."""
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "method": "POST",
        "path": "/artifact", "query_string": b"", "headers": [],
    }
    events = [
        {"type": "http.request", "body": uf2[:100], "more_body": True},
        {"type": "http.disconnect"},
    ]
    sent = []

    async def receive():
        return events.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    assert sent == []


def test_an_unsupported_scope_type_is_refused(app):
    """A websocket connection to an app that does not speak it. Better a clear
    NotImplementedError than a silent hang while a client waits for an accept
    that never comes."""
    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        raise AssertionError("nothing should be sent")

    with pytest.raises(NotImplementedError):
        asyncio.run(app({"type": "websocket", "path": "/ws"}, receive, send))
