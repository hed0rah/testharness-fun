"""The same app, through httpx.ASGITransport and Starlette's TestClient.

Compare against test_asgi_raw.py. The assertions are the same assertions; only
the four lines that issue the request changed. That is the property you want
from a test client -- it should be a convenience, not a place where behaviour
lives.

What the framework clients give you that the raw harness does not:

    httpx.ASGITransport   real header handling, cookies, redirects, content
                          negotiation, and a request/response API identical to
                          the one your production client code uses
    TestClient            all of that plus lifespan handled by a context
                          manager, and a synchronous API over an async app

What they take away: control of the chunking, the ability to send a malformed
scope, and visibility of the protocol. Which is why both files exist.

Both are gated with `importorskip`. fwvault has no runtime dependencies, so a
bare `pip install -e .` runs everything else in this suite and skips exactly
this file, with a reason that prints. That is the shape to copy: an optional
stack means optional tests, not a suite that fails to collect.
"""

import pytest

from fwvault.app import create_app
from fwvault.errors import VaultUnavailable
from fwvault.testing import UNKNOWN_FAMILY, build_uf2

httpx = pytest.importorskip("httpx", reason="the httpx client tests need httpx")


# ── httpx.ASGITransport, async ──────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    """anyio's pytest plugin parametrizes over backends via this fixture.
    Pinning it to asyncio keeps the run from also spawning a trio pass that
    would need trio installed."""
    return "asyncio"


@pytest.fixture
async def http(app):
    """An httpx client wired straight into the app object. No socket, no port,
    no server process -- ASGITransport calls the app the same way uvicorn
    would.

    An async fixture, which needs an async plugin (anyio's, here). That is the
    usual reason a working async test suddenly reports "coroutine was never
    awaited": the plugin is missing and pytest collected the coroutine as if it
    were a test function.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://vault") as client:
        yield client


@pytest.mark.anyio
async def test_healthz_over_httpx(http):
    response = await http.get("/healthz")
    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.anyio
async def test_ingest_over_httpx(http, uf2):
    response = await http.post("/artifact", content=uf2)
    assert response.status_code == 201
    assert response.json()["created"] is True


@pytest.mark.anyio
async def test_headers_survive_the_client(http, uf2):
    """The client normalises header case, which the raw harness did by hand.
    Worth one test: it is the sort of thing a hand-rolled harness gets subtly
    wrong and then hides."""
    response = await http.post(
        "/artifact", content=uf2, headers={"X-FwVault-Flags": "0x1"}
    )
    assert response.json()["error"] == "NOT_MAIN_FLASH"


@pytest.mark.anyio
async def test_policy_rejection_over_httpx(http):
    response = await http.post(
        "/artifact", content=build_uf2(blocks=1, family=UNKNOWN_FAMILY)
    )
    assert response.status_code == 422
    assert response.json()["error"] == "UNKNOWN_FAMILY"


@pytest.mark.anyio
async def test_retry_after_header_is_visible_to_a_real_client(vault, policy, uf2):
    """Asserted through a client this time, because a header the raw harness
    can see and a client strips is a bug the raw harness cannot report."""
    class DeadClient:
        def verify(self, digest):
            raise VaultUnavailable("oracle down")

    app = create_app(store=vault, client=DeadClient(), policy=policy)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://vault") as client:
        response = await client.post("/artifact", content=uf2)

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


# ── httpx.MockTransport, the other direction ────────────────────────────────

def test_mock_transport_fakes_the_far_side(clock):
    """ASGITransport substitutes the SERVER. MockTransport substitutes the
    THING WE CALL. Same library, opposite ends of the wire, and the two get
    confused constantly.

    This is the httpx-native equivalent of the RecordingTransport in
    fwvault.testing -- worth seeing side by side, because the hand-rolled one
    is four lines and this one gives you a real Request object with real header
    parsing for free.
    """
    from fwvault.signing import Response as FwResponse
    from fwvault.signing import SigningClient

    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"signed": True, "signer": "ci-builder",
                                         "key_id": "k-2f81", "revoked": False})

    httpx_client = httpx.Client(transport=httpx.MockTransport(handler))

    class HttpxAdapter:
        """The seam is ours, so adapting httpx to it is four lines. A package
        that made httpx.Response its interface would instead have to make every
        test import httpx."""

        def request(self, method, url, body=None, headers=None):
            response = httpx_client.request(method, url, content=body, headers=headers)
            return FwResponse(response.status_code, response.content, dict(response.headers))

    verdict = SigningClient("https://oracle.example.com",
                            transport=HttpxAdapter(), clock=clock).verify("a" * 64)

    assert verdict.signer == "ci-builder"
    assert str(seen[0].url) == "https://oracle.example.com/keys/" + "a" * 64
    assert seen[0].headers["accept"] == "application/json"


# ── Starlette's TestClient ──────────────────────────────────────────────────

def test_starlette_testclient_drives_the_raw_app(app, uf2):
    """TestClient wraps ANY ASGI app, not only a Starlette one. This app has
    never heard of Starlette and the client does not care -- which is the whole
    argument for coding to the protocol rather than to a framework.

    The context manager is what runs lifespan. Without it, startup never fires;
    with it, an app that does not answer lifespan hangs here rather than in
    production.
    """
    starlette = pytest.importorskip("starlette", reason="needs starlette")
    from starlette.testclient import TestClient

    assert starlette.__version__

    with TestClient(app) as client:
        assert client.get("/healthz").json()["ok"] is True

        posted = client.post("/artifact", content=uf2)
        assert posted.status_code == 201

        manifest = client.get("/vault/" + posted.json()["digest"])
        assert manifest.json()["family"] == "RP2040"


def test_testclient_reports_the_rejection_the_same_way(app):
    """Identical to the raw-harness assertion, and to the httpx one. Three
    clients, one behaviour -- if these ever disagree, the disagreement is the
    finding."""
    pytest.importorskip("starlette", reason="needs starlette")
    from starlette.testclient import TestClient

    with TestClient(app) as client:
        response = client.post("/artifact", content=build_uf2(blocks=1, family=UNKNOWN_FAMILY))

    assert response.status_code == 422
    assert response.json()["error"] == "UNKNOWN_FAMILY"
