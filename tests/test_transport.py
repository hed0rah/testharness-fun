"""The transport seam: retries, staleness, and the one test that really talks.

Everything here drives `SigningClient` through a substituted transport, which
is the pattern this package is built for. The interesting assertions are not
"it returned a Verdict" -- they are about WHEN, HOW OFTEN, and WHAT IT DID NOT
DO, and none of those are visible in a return value.

The last test in the file is marked `net`. It makes a real connection and is
deselected everywhere by default (see conftest.pytest_collection_modifyitems).
That is deliberate honesty: `UrllibTransport` cannot be covered by a fake of
itself, so rather than pretend otherwise, the gap is a named test with a skip
reason that prints on every run.
"""

import pytest

from fwvault.errors import VaultUnavailable
from fwvault.signing import (
    Response,
    SigningClient,
    TransportError,
    UrllibTransport,
    Verdict,
)
from fwvault.testing import RecordingTransport, ScriptedTransport, flaky, signed_body


# ── the happy path ──────────────────────────────────────────────────────────

def test_a_200_becomes_a_verdict(clock):
    transport = RecordingTransport(routes={"": Response(200, signed_body())})
    client = SigningClient("https://x", transport=transport, clock=clock)
    assert client.verify("a" * 64) == Verdict(
        signed=True, signer="ci-builder", key_id="k-2f81"
    )


def test_the_url_is_built_from_the_base_and_the_digest(clock):
    transport = RecordingTransport(routes={"": Response(200, signed_body())})
    SigningClient("https://oracle.example.com/", transport=transport, clock=clock).verify("ab")
    assert transport.urls == ["https://oracle.example.com/keys/ab"]


def test_no_sleep_on_the_first_attempt(clock):
    """Off-by-one in a backoff loop costs every caller half a second on the
    happy path, and no return value shows it."""
    transport = RecordingTransport(routes={"": Response(200, signed_body())})
    SigningClient("https://x", transport=transport, clock=clock).verify("ab")
    assert clock.slept == []


# ── status handling ─────────────────────────────────────────────────────────

def test_404_is_a_definite_unsigned(clock):
    """The oracle has never seen this digest. That is an answer, so it is not
    retried and it is not an outage."""
    transport = RecordingTransport(default=Response(404, b"{}"))
    client = SigningClient("https://x", transport=transport, clock=clock)
    assert client.verify("a" * 64) == Verdict(signed=False)
    assert len(transport.calls) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 422], ids=lambda s: str(s))
def test_client_errors_from_the_oracle_are_our_problem(status, clock):
    """A 401 from the oracle means OUR credentials are wrong. Rendering that as
    "this artifact is unsigned" blames the user for our misconfiguration, and
    is the exact shape of bug this taxonomy exists to prevent."""
    transport = RecordingTransport(default=Response(status, b"{}"))
    client = SigningClient("https://x", transport=transport, clock=clock)
    with pytest.raises(VaultUnavailable, match=str(status)):
        client.verify("a" * 64)
    assert len(transport.calls) == 1, "a 4xx is not retried; it will not change"


@pytest.mark.parametrize("status", [500, 502, 503], ids=lambda s: str(s))
def test_5xx_is_retried(status, clock):
    transport = RecordingTransport(default=Response(status, b"{}"))
    client = SigningClient("https://x", transport=transport, clock=clock, retries=3)
    with pytest.raises(VaultUnavailable):
        client.verify("a" * 64)
    assert len(transport.calls) == 3


# ── the retry schedule ──────────────────────────────────────────────────────

def test_backoff_is_exponential_and_instant(clock):
    """The schedule is the behaviour. Asserting it takes zero wall-clock time
    because the clock is injected -- a real sleep here would put 3.5 seconds
    into every CI run to test arithmetic.

    Note what is NOT asserted: that the sleeps happened between the right
    calls. If that ordering ever matters, interleave by recording into one
    shared list from both the clock and the transport."""
    script = ScriptedTransport(flaky(3, Response(200, signed_body())))
    client = SigningClient("https://x", transport=script, clock=clock, retries=4)
    client.verify("a" * 64)
    assert clock.slept == [0.5, 1.0, 2.0]


def test_backoff_base_is_configurable(clock):
    script = ScriptedTransport(flaky(2, Response(200, signed_body())))
    client = SigningClient("https://x", transport=script, clock=clock, retries=3, backoff=0.1)
    client.verify("a" * 64)
    assert clock.slept == [0.1, 0.2]


def test_retries_are_bounded(clock):
    """`retries=2` means two attempts, not two retries after the first. Which
    one it means is a decision, and an untested one is a decision nobody made
    -- this is where an off-by-one becomes a doubled load on a service that is
    already failing."""
    script = ScriptedTransport([TransportError("reset")] * 2)
    client = SigningClient("https://x", transport=script, clock=clock, retries=2)
    with pytest.raises(VaultUnavailable):
        client.verify("a" * 64)
    assert len(script.calls) == 2
    assert script.exhausted


# ── the cache, and telling a stale yes from a fresh one ─────────────────────

def test_a_cached_answer_is_served_when_the_oracle_dies(clock):
    """First call succeeds and populates the cache; the oracle then falls over.
    The client answers from cache rather than failing the build."""
    cache = {}
    good = SigningClient("https://x", transport=RecordingTransport(
        routes={"": Response(200, signed_body())}), clock=clock, cache=cache)
    good.verify("a" * 64)

    dead = SigningClient("https://x", transport=ScriptedTransport(
        [TransportError("down")] * 3), clock=clock, retries=3, cache=cache)
    verdict = dead.verify("a" * 64)
    assert verdict.signed is True


def test_a_stale_answer_says_it_is_stale(clock):
    """And the flag is the whole point. A cached yes served during an outage is
    useful; a cached yes that presents as fresh is a lie with a timestamp on
    it, and the API surfaces it as `stale_verdict` for exactly this reason.

    Asserted separately from the test above because these are two behaviours:
    one is availability, one is honesty, and a change that keeps the first and
    drops the second should fail one test with an obvious name."""
    cache = {}
    SigningClient("https://x", transport=RecordingTransport(
        routes={"": Response(200, signed_body())}), clock=clock, cache=cache).verify("a" * 64)

    dead = SigningClient("https://x", transport=ScriptedTransport(
        [TransportError("down")] * 3), clock=clock, retries=3, cache=cache)
    assert dead.verify("a" * 64).stale is True


def test_an_empty_cache_during_an_outage_raises(clock):
    """No cached answer and no oracle means we do not know. The service says
    503; it does not guess."""
    dead = SigningClient("https://x", transport=ScriptedTransport(
        [TransportError("down")] * 3), clock=clock, retries=3)
    with pytest.raises(VaultUnavailable):
        dead.verify("never-seen")


# ── logging, via caplog ─────────────────────────────────────────────────────

def test_a_retry_is_logged(caplog, clock):
    """`caplog` captures log records. Two things people miss.

    First, set the level: pytest captures at WARNING by default, so an
    `log.info(...)` you are asserting on never arrives and the test fails
    looking like the code is wrong.

    Second, assert on `caplog.records`, not on `caplog.text`. A record has
    `.levelname`, `.name` and `.getMessage()`; the text blob has whatever the
    formatter felt like. Asserting on formatted text couples the test to a
    format string nobody thinks of as an interface.
    """
    import logging

    caplog.set_level(logging.WARNING, logger="fwvault.signing")

    script = ScriptedTransport(flaky(2, Response(200, signed_body())))
    SigningClient("https://x", transport=script, clock=clock, retries=3).verify("a" * 64)

    retries = [r for r in caplog.records if "attempt" in r.getMessage()]
    assert len(retries) == 2
    assert all(r.levelname == "WARNING" for r in retries)
    assert all(r.name == "fwvault.signing" for r in retries)


def test_serving_a_stale_verdict_is_logged_loudly(caplog, clock):
    """The stale path is the one that must never be silent. A cached yes served
    during an outage is a decision the operator has to be able to find
    afterwards, so it is a WARNING and it says STALE."""
    import logging

    caplog.set_level(logging.WARNING, logger="fwvault.signing")

    cache = {}
    SigningClient("https://x", transport=RecordingTransport(
        routes={"": Response(200, signed_body())}), clock=clock,
        cache=cache).verify("a" * 64)

    dead = SigningClient("https://x", transport=ScriptedTransport(
        [TransportError("down")] * 3), clock=clock, retries=3, cache=cache)
    caplog.clear()
    dead.verify("a" * 64)

    stale = [r for r in caplog.records if "STALE" in r.getMessage()]
    assert len(stale) == 1
    assert stale[0].levelname == "WARNING"


def test_the_happy_path_logs_nothing(caplog, clock):
    """The negative case, and the one that keeps a service usable. A log line
    on every successful request is a log nobody reads, which is the same as no
    log at all when something finally goes wrong."""
    import logging

    caplog.set_level(logging.DEBUG, logger="fwvault.signing")
    SigningClient("https://x", transport=RecordingTransport(
        routes={"": Response(200, signed_body())}), clock=clock).verify("a" * 64)

    assert caplog.records == []


# ── the untestable edge, named rather than hidden ───────────────────────────

@pytest.mark.net
def test_urllib_transport_against_a_real_server():
    """The one thing no fake can cover: that UrllibTransport speaks HTTP.

    Deselected by default; `pytest --runnet` opts in. The skip reason prints on
    every run because pyproject sets -rs, so the gap stays visible instead of
    being quietly covered by a fake of the very class under test.
    """
    transport = UrllibTransport(timeout=5.0)
    response = transport.request("GET", "https://example.com/")
    assert response.status == 200


def test_urllib_transport_converts_socket_errors(monkeypatch):
    """What CAN be tested without a socket: that the error TRANSLATION is right.

    urlopen is patched here rather than injected, and this is the case where
    patching is correct -- urllib is not our seam, we do not own it, and there
    is no argument to pass. That is the rule: patch what you do not own.
    """
    import urllib.request

    def boom(*args, **kwargs):
        raise OSError("network is unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(TransportError, match="unreachable"):
        UrllibTransport().request("GET", "https://x/")
