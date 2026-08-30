"""The ASGI application, hand-rolled.

There is no Starlette here, and that is pedagogical rather than principled. An
ASGI app is a coroutine taking three arguments:

    async def app(scope, receive, send)

`scope` is a dict describing the connection, `receive` is an awaitable you call
to pull events in, `send` is a coroutine you call to push events out. That is
the whole protocol. Every framework you have used is a very good router and
middleware stack wrapped around those three names, and every test client you
have used -- Starlette's TestClient, httpx's ASGITransport -- is something that
builds a scope, feeds a receive, and collects the sends.

Seeing it undressed once makes the framework versions legible, and it means
tests/test_asgi_raw.py can drive this app with about twenty lines of harness
and no dependencies at all. tests/test_asgi_httpx.py then drives the SAME app
through httpx.ASGITransport, and the assertions barely change. That is the
point: if swapping the client changes your assertions, you were testing the
client.

`create_app` takes its collaborators as arguments. There is no module-level
store, no global client, and no settings singleton, so two tests can run two
differently-configured apps in the same process without touching each other.
"""

import json
import re

from . import policy as policy_mod
from .errors import ParseError, PolicyRejection, VaultUnavailable
from .parse import parse
from .store import SCHEMA_VERSION, Manifest, Store, digest_of

MAX_BODY = 8 * 1024 * 1024


class Request:
    """Just enough request. Built by the router, handed to a handler."""

    def __init__(self, scope, body, params):
        self.scope = scope
        self.body = body
        self.params = params
        self.headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }



class Router:
    """Method + path pattern -> handler.

    Patterns use `{name}`, compiled once at registration. The compiled regex is
    anchored at both ends: an unanchored router is how `/vault/{d}` starts
    matching `/vault/abc/../../admin`, and that is a routing bug wearing a
    security bug's clothes.
    """

    def __init__(self):
        self.routes = []

    def add(self, method, pattern, handler):
        regex = re.compile(
            "^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$"
        )
        self.routes.append((method, regex, handler, pattern))
        return handler

    def resolve(self, method, path):
        """Returns (handler, params) or (None, reason).

        The reason distinguishes 404 from 405, which matters: a client that
        gets 404 for a POST to a GET-only path will retry forever looking for a
        path that is right there.
        """
        path_matched = False
        for route_method, regex, handler, _pattern in self.routes:
            match = regex.match(path)
            if not match:
                continue
            path_matched = True
            if route_method == method:
                return handler, match.groupdict()
        return None, ("method_not_allowed" if path_matched else "not_found")


def create_app(store=None, client=None, policy=None, max_body=MAX_BODY):
    """Build an app over the given collaborators. Every one is a parameter."""
    store = store if store is not None else Store(".fwvault")
    policy = policy if policy is not None else policy_mod.DEFAULT
    router = Router()

    async def healthz(request):
        return 200, {"ok": True, "schema_version": SCHEMA_VERSION}

    async def ingest(request):
        """The whole pipeline, and the whole error taxonomy, in one handler."""
        if not request.body:
            return 400, {"error": "EMPTY_BODY", "detail": "no bytes in request body"}

        try:
            image = parse(request.body)
        except ParseError as exc:
            # A fact about the artifact. Deterministic, client-fixable, 422.
            return 422, {
                "error": "MALFORMED",
                "detail": str(exc),
                "offset": exc.offset,
            }

        digest = digest_of(request.body)

        verdict = None
        if client is not None:
            try:
                verdict = client.verify(digest)
            except VaultUnavailable as exc:
                # A fact about US. 503 and a Retry-After, never a rejection.
                # Rendering this as UNSIGNED is the bug this whole service is
                # shaped to avoid; see errors.py.
                return 503, {"error": "ORACLE_UNAVAILABLE", "detail": str(exc)}

        try:
            flags = int(request.headers.get("x-fwvault-flags", "0"), 0)
        except ValueError:
            return 400, {"error": "BAD_HEADER", "detail": "x-fwvault-flags is not an integer"}

        try:
            policy_mod.enforce(image, verdict, policy, flags)
        except PolicyRejection as exc:
            return 422, {"error": exc.code, "detail": exc.detail}

        manifest = Manifest(
            digest=digest,
            kind=image.kind,
            size=image.size,
            family=image.family,
            entry=image.entry,
            signer=verdict.signer if verdict else None,
            warnings=tuple(image.warnings),
        )
        _digest, created = store.put(request.body, manifest)
        return (201 if created else 200), {
            "digest": digest,
            "created": created,
            "warnings": list(image.warnings),
            "stale_verdict": bool(verdict and verdict.stale),
        }

    async def fetch(request):
        digest = request.params["digest"]
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            return 400, {"error": "BAD_DIGEST", "detail": "not a sha256 hex digest"}
        if not store.has(digest):
            return 404, {"error": "NOT_FOUND", "detail": digest}
        return 200, store.manifest(digest)

    router.add("GET", "/healthz", healthz)
    router.add("POST", "/artifact", ingest)
    router.add("GET", "/vault/{digest}", fetch)

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            # Startup and shutdown. Handled rather than ignored, because a test
            # client that sends lifespan events to an app that does not answer
            # them hangs, and a hanging test is a worse bug than a failing one.
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
            return

        if scope["type"] != "http":
            raise NotImplementedError("only http and lifespan scopes")

        body = b""
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body += message.get("body", b"")
            more = message.get("more_body", False)
            if len(body) > max_body:
                # Refuse before buffering the rest. Testing this needs a
                # receive() that yields more than one chunk, which is why the
                # raw harness in tests/ can send a chunk list.
                return await _respond(
                    send, 413,
                    {"error": "OVERSIZE", "detail": "body exceeds {} bytes".format(max_body)},
                )

        handler, params = router.resolve(scope["method"], scope["path"])
        if handler is None:
            status = 405 if params == "method_not_allowed" else 404
            return await _respond(send, status, {"error": params.upper()})

        status, payload = await handler(Request(scope, body, params))
        await _respond(send, status, payload)

    app.router = router          # tests introspect the table; see test_contract.py
    app.store = store
    return app


async def _respond(send, status, payload):
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if status == 503:
        headers.append((b"retry-after", b"5"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
