"""The five test doubles, with a working example of each and when it is wrong.

The words are Gerard Meszaros's, and they are worth using precisely because
"mock" has become a verb meaning "any object I made up". The distinction is not
pedantry: it predicts how your test fails.

    dummy    passed to satisfy a signature, never used
    stub     returns canned answers, no state worth asking about
    fake     a real, working, simplified implementation
    spy      a stub that records how it was called
    mock     a spy with expectations built in; it asserts on itself

Rule of thumb this suite follows: prefer a FAKE, fall back to a SPY, reach for
a MOCK almost never. A mock fails inside the double, so the failure message
describes a call that did not happen rather than a behaviour that is wrong, and
the assertion lives in the setup section where nobody looks for it.

The deeper reason to prefer fakes: a stub or mock encodes your belief about
what the collaborator does. When that belief goes stale -- the API changed, the
status code is different now -- the double keeps agreeing with you and the
suite stays green against a service that no longer exists. That failure mode
has a name, and tests/test_contract.py is where this suite pays for it.
"""

import pytest

from fwvault.errors import VaultUnavailable
from fwvault.policy import evaluate
from fwvault.signing import Response, SigningClient, TransportError, Verdict
from fwvault.testing import (
    RecordingTransport,
    ScriptedTransport,
    build_uf2,
    signed_body,
)
from fwvault.parse import parse


# ── dummy ───────────────────────────────────────────────────────────────────

def test_dummy_verdict_is_never_read():
    """`evaluate` takes a verdict it does not use when the policy does not ask
    for a signature. Passing None is the dummy: it exists to fill the slot.

    If a dummy's value ever starts mattering, the test silently changes meaning
    -- which is why the name is worth having."""
    from dataclasses import replace

    from fwvault.policy import DEFAULT

    image = parse(build_uf2(blocks=1))
    unchecked = replace(DEFAULT, require_signature=False)
    assert evaluate(image, None, unchecked) == ()


# ── stub ────────────────────────────────────────────────────────────────────

class StubTransport:
    """Canned answer, no memory, no behaviour. Four lines, and that is the
    point: when all a test needs is "the oracle says yes", anything richer is
    scenery."""

    def __init__(self, response):
        self.response = response

    def request(self, method, url, body=None, headers=None):
        return self.response


def test_stub_supplies_an_answer():
    client = SigningClient("https://x", transport=StubTransport(Response(200, signed_body())))
    assert client.verify("deadbeef").signer == "ci-builder"


def test_stub_cannot_tell_you_the_url_was_right():
    """The stub's limitation, stated as a test.

    This passes with a client that builds a nonsense URL, because the stub
    answers everything identically. If the URL matters, you need a spy -- and
    the next test is that spy."""
    client = SigningClient("https://x", transport=StubTransport(Response(200, signed_body())))
    assert client.verify("deadbeef").signed is True


# ── spy ─────────────────────────────────────────────────────────────────────

def test_spy_records_the_request_that_was_made(clock):
    """RecordingTransport is a spy: it answers AND remembers. Now the URL is
    assertable, and it is asserted where the reader can see it rather than
    inside the double."""
    spy = RecordingTransport(routes={"": Response(200, signed_body())})
    client = SigningClient("https://oracle.example.com", transport=spy, clock=clock)
    client.verify("a" * 64)

    assert spy.urls == ["https://oracle.example.com/keys/" + "a" * 64]
    method, _url, body, headers = spy.calls[0]
    assert method == "GET"
    assert body is None
    assert headers["accept"] == "application/json"


def test_spy_proves_a_call_did_not_happen(clock):
    """The negative assertion, which is where spies beat return-value checks.

    "the cache was used" is invisible in the returned Verdict and obvious in
    the call log."""
    spy = RecordingTransport(routes={"": Response(200, signed_body())})
    client = SigningClient("https://x", transport=spy, clock=clock)
    client.verify("b" * 64)
    client.verify("b" * 64)
    assert len(spy.calls) == 2, "verify() is not supposed to short-circuit on a hit"


# ── fake ────────────────────────────────────────────────────────────────────

class FakeOracle:
    """A working oracle, in memory. Real routing, real 404s, real JSON.

    This is the double to reach for. It is the only kind that can be WRONG in a
    way a test notices: a stub returning 200 forever cannot fail to model a
    404, because it was never modelling anything.
    """

    def __init__(self, known=None):
        self.known = dict(known or {})

    def request(self, method, url, body=None, headers=None):
        digest = url.rsplit("/", 1)[-1]
        if digest not in self.known:
            return Response(404, b'{"error":"unknown digest"}')
        signer = self.known[digest]
        return Response(200, signed_body(signer=signer))


def test_fake_models_both_outcomes(clock):
    fake = FakeOracle({"a" * 64: "ci-builder"})
    client = SigningClient("https://x", transport=fake, clock=clock)

    assert client.verify("a" * 64).signer == "ci-builder"
    assert client.verify("f" * 64).signed is False


def test_fake_404_is_a_definite_no_not_an_outage(clock):
    """The behaviour that matters most, and it is only expressible because the
    fake distinguishes "not found" from "could not ask". A stub cannot state
    this distinction, so a suite built on stubs never checks it -- and that is
    exactly the bug this service is shaped around."""
    client = SigningClient("https://x", transport=FakeOracle(), clock=clock)
    verdict = client.verify("f" * 64)
    assert verdict == Verdict(signed=False)


# ── mock ────────────────────────────────────────────────────────────────────

def test_mock_asserts_on_itself_and_that_is_the_problem(clock):
    """unittest.mock, used the way people actually use it, with the failure
    mode visible.

    `assert_called_once_with` is an assertion living inside the double. When it
    fails you get "Expected call: request('GET', ...)" and nothing about which
    behaviour of the system is wrong. Compare the spy tests above, which fail
    with a URL diff.

    The second half is worse: a Mock answers ANY attribute access with another
    Mock, so a typo'd method name passes silently. `spec=` is not optional.
    """
    from unittest.mock import Mock

    transport = Mock(spec=["request"])
    transport.request.return_value = Response(200, signed_body())

    client = SigningClient("https://x", transport=transport, clock=clock)
    client.verify("c" * 64)

    transport.request.assert_called_once_with(
        "GET", "https://x/keys/" + "c" * 64, headers={"accept": "application/json"}
    )
    with pytest.raises(AttributeError):
        transport.reqeust                       # the typo `spec=` catches


def test_a_mock_without_spec_accepts_anything():
    """Left in deliberately, as the demonstration. Every attribute exists,
    every call succeeds, and a test built on this asserts nothing about a real
    object's surface."""
    from unittest.mock import Mock

    loose = Mock()
    loose.this_method_does_not_exist().nor_does_this_one()
    assert loose.anything_at_all is not None


# ── scripted, for sequences ─────────────────────────────────────────────────

def test_scripted_transport_drives_a_retry_sequence(clock):
    """When WHEN matters, the double needs a sequence rather than a value.

    Three attempts: fail, fail, succeed. The assertion is on both the result
    and the schedule, because a client that retried instantly would satisfy the
    first half alone."""
    script = ScriptedTransport([
        TransportError("reset"),
        TransportError("reset"),
        Response(200, signed_body()),
    ])
    client = SigningClient("https://x", transport=script, clock=clock, retries=3)

    assert client.verify("d" * 64).signed is True
    assert script.exhausted
    assert clock.slept == [0.5, 1.0]


def test_running_off_the_end_of_a_script_is_a_failure(clock):
    """A double that keeps answering after its script runs out turns "retried
    3 times" and "retried 300 times" into the same passing test. This one
    refuses, loudly, and names the call number."""
    script = ScriptedTransport([TransportError("reset")])
    client = SigningClient("https://x", transport=script, clock=clock, retries=5)
    with pytest.raises(AssertionError, match="ScriptedTransport exhausted"):
        client.verify("e" * 64)


def test_exhausted_retries_raise_unavailable_not_unsigned(clock):
    """The headline. Three transport failures and no cache produce
    VaultUnavailable, never Verdict(signed=False).

    Getting this wrong converts a signing-oracle outage into a wall of
    confident rejections that look exactly like real ones, and nobody finds it
    until someone asks why every build failed overnight."""
    script = ScriptedTransport([TransportError("reset")] * 3)
    client = SigningClient("https://x", transport=script, clock=clock, retries=3)
    with pytest.raises(VaultUnavailable):
        client.verify("0" * 64)
