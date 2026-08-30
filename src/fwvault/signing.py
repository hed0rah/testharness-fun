"""The outbound half: asking a signing oracle whether a digest is vouched for.

This module exists in the shape it does because of one rule -- the thing that
talks to the network is a parameter, not an import. `SigningClient` never
mentions urllib, sockets or hosts. It holds a `transport` with a single
`request` method, and the real one is just the default argument.

That is the entire trick behind every "mock transport" test you will read
below. Nothing is patched, nothing is monkeyed, no import machinery is
involved: the test passes a different object. Patching enters later, in
tests/test_monkeypatch.py, for the cases where you do NOT own the seam.
"""

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

from .clock import SystemClock
from .errors import VaultUnavailable

# A module logger, not the root logger. `logging.warning(...)` at module level
# configures the root handler as a side effect and steals output formatting
# from whatever application imported us. tests/test_transport.py asserts on
# these records through caplog.
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Response:
    """A transport's answer. Deliberately not an httpx.Response: the narrower
    the seam, the cheaper the fake that fills it."""

    status: int
    body: bytes
    headers: dict = None

    def json(self):
        return json.loads(self.body.decode("utf-8"))


@dataclass(frozen=True)
class Verdict:
    """What the oracle said. `stale` records that we answered from cache after
    the oracle went away, so a caller can tell a fresh no from an old yes."""

    signed: bool
    signer: str | None = None
    key_id: str | None = None
    revoked: bool = False
    stale: bool = False


class TransportError(Exception):
    """The request did not complete. Distinct from a completed request that
    returned 500 -- the retry policy treats them the same, but the log line
    and the test that asserts on it do not."""


class UrllibTransport:
    """The real one. Stdlib, so the package has no runtime dependencies.

    There is no test for this class that runs by default, and that is the
    honest position: exercising it means a socket. tests/test_transport.py has
    one marked `net`, deselected everywhere, which is how you keep an untested
    edge visible instead of pretending the fake covered it.
    """

    def __init__(self, timeout=5.0):
        self.timeout = timeout

    def request(self, method, url, body=None, headers=None):
        req = urllib.request.Request(
            url, data=body, headers=headers or {}, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return Response(resp.status, resp.read(), dict(resp.headers))
        except urllib.error.HTTPError as exc:      # a completed request, bad status
            return Response(exc.code, exc.read(), dict(exc.headers))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransportError(str(exc)) from exc


class SigningClient:
    """Ask the oracle about a digest, with bounded retries.

    The retry schedule is the interesting testable surface, and it is only
    testable because `clock` is injected: a test asserts the client slept
    0.5, 1.0 and 2.0 seconds without any of those seconds passing.
    """

    def __init__(self, base_url, transport=None, clock=None, retries=3,
                 backoff=0.5, cache=None):
        self.base_url = base_url.rstrip("/")
        self.transport = transport or UrllibTransport()
        self.clock = clock or SystemClock()
        self.retries = retries
        self.backoff = backoff
        self.cache = {} if cache is None else cache

    def verify(self, digest):
        """Return a Verdict, or raise VaultUnavailable.

        Never returns `Verdict(signed=False)` because the oracle was down. That
        is the single most important line in this file: an outage that renders
        as "unsigned" turns into a wall of confident refusals indistinguishable
        from real ones, and nobody finds it until someone asks why every build
        failed at 3am.
        """
        url = "{}/keys/{}".format(self.base_url, digest)
        last = None

        for attempt in range(self.retries):
            if attempt:
                self.clock.sleep(self.backoff * (2 ** (attempt - 1)))
            try:
                resp = self.transport.request("GET", url, headers={"accept": "application/json"})
            except TransportError as exc:
                last = exc
                log.warning("signing oracle attempt %d/%d failed: %s",
                            attempt + 1, self.retries, exc)
                continue

            if resp.status == 200:
                data = resp.json()
                verdict = Verdict(
                    signed=bool(data.get("signed")),
                    signer=data.get("signer"),
                    key_id=data.get("key_id"),
                    revoked=bool(data.get("revoked")),
                )
                self.cache[digest] = verdict
                return verdict
            if resp.status == 404:
                # A definite answer: the oracle has never seen this digest.
                verdict = Verdict(signed=False)
                self.cache[digest] = verdict
                return verdict
            if resp.status < 500:
                raise VaultUnavailable(
                    "signing oracle refused the query: {}".format(resp.status)
                )
            last = TransportError("status {}".format(resp.status))

        cached = self.cache.get(digest)
        if cached is not None:
            # Answer from cache, but say so. A stale yes is useful; a stale yes
            # that pretends to be fresh is a lie with a timestamp on it.
            log.warning("serving STALE verdict for %s: oracle unreachable", digest[:12])
            return Verdict(
                signed=cached.signed, signer=cached.signer,
                key_id=cached.key_id, revoked=cached.revoked, stale=True,
            )
        raise VaultUnavailable(
            "signing oracle unreachable after {} attempts: {}".format(self.retries, last)
        )
