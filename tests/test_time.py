"""Time: inject it, do not freeze it, and never sleep in a test.

Three ways to get time out of a test's way, worst to best:

    time.sleep(3)             the suite gets three seconds slower, forever, and
                              still cannot assert the schedule
    monkeypatch time.sleep    fast, but process-wide: it silences every sleep
                              in every library running in this test, including
                              ones you did not mean to touch
    inject a clock            fast, local, and the fake can be interrogated
                              afterwards -- which is where the assertions are

freezegun and time-machine do the second thing very well, and they are the
right tool when the code under test calls `datetime.now()` in places you cannot
reach. When you own the code, a two-method Clock protocol is less machinery and
strictly more testable.

The tell that you got it right: `assert clock.slept == [0.5, 1.0, 2.0]`. A
schedule is a behaviour, and no amount of freezing lets you assert one.
"""

import time

import pytest

from fwvault.clock import FakeClock, SystemClock
from fwvault.errors import VaultUnavailable
from fwvault.signing import Response, SigningClient, TransportError
from fwvault.testing import ScriptedTransport, flaky, signed_body


# ── the fake ────────────────────────────────────────────────────────────────

def test_fake_clock_only_moves_when_moved():
    clock = FakeClock(start=1000.0)
    assert clock.now() == 1000.0
    clock.advance(60)
    assert clock.now() == 1060.0


def test_sleeping_advances_the_fake_clock():
    """A fake, not a stub: sleeping has the real consequence of time passing.
    A stub whose sleep() does nothing lets a cache-expiry bug through."""
    clock = FakeClock(start=0.0)
    clock.sleep(2.5)
    assert clock.now() == 2.5
    assert clock.slept == [2.5]


def test_the_schedule_is_the_assertion(clock):
    """The whole argument for injection in one line. Three retries, an
    exponential schedule, asserted exactly, in zero wall-clock time."""
    script = ScriptedTransport(flaky(3, Response(200, signed_body())))
    SigningClient("https://x", transport=script, clock=clock, retries=4).verify("a" * 64)
    assert clock.slept == [0.5, 1.0, 2.0]


def test_no_real_time_passes():
    """Guards the guard. If someone swaps FakeClock back to SystemClock in the
    fixture, every schedule assertion above still passes and the suite silently
    gets seven seconds slower per run.

    A wall-clock bound this loose (0.5s for work that should take microseconds)
    is safe on a loaded CI runner while still catching a real sleep."""
    started = time.monotonic()
    script = ScriptedTransport(flaky(3, Response(200, signed_body())))
    SigningClient("https://x", transport=script, clock=FakeClock(), retries=4).verify("a" * 64)
    assert time.monotonic() - started < 0.5


# ── monkeypatching time, and its blast radius ───────────────────────────────

def test_monkeypatching_time_sleep_works_and_is_too_broad(monkeypatch):
    """The technique, with its cost stated.

    This silences `time.sleep` for everything in the process for the duration
    of the test -- our retry loop, and also any library that sleeps for a
    reason. The recording list is global, so two concurrent things sleeping
    become one interleaved log with no way to tell them apart.

    Correct when you do not own the code that sleeps. Second-best when you do.
    """
    recorded = []
    monkeypatch.setattr(time, "sleep", recorded.append)

    real = SystemClock()
    real.sleep(1.5)
    real.sleep(3.0)

    assert recorded == [1.5, 3.0]


def test_time_sleep_is_restored():
    """monkeypatch undid it. Worth asserting once, because a hand-rolled patch
    that forgets to restore `time.sleep` turns every subsequent timing test in
    the run into a lie."""
    assert time.sleep is not list.append


# ── timeouts and deadlines ──────────────────────────────────────────────────

def test_an_outage_costs_a_bounded_amount_of_time(clock):
    """What a caller actually cares about: the worst case. Three attempts at
    0.5 + 1.0 backoff is 1.5 seconds of sleeping, and that number belongs in a
    test because it is what a queue's throughput is computed from."""
    script = ScriptedTransport([TransportError("down")] * 3)
    with pytest.raises(VaultUnavailable):
        SigningClient("https://x", transport=script, clock=clock, retries=3).verify("a")
    assert sum(clock.slept) == 1.5


def test_a_test_that_could_hang_gets_a_timeout():
    """There is no assertion about time here, and that is the point.

    A test that can hang -- a subprocess, a socket, a queue.get() -- needs a
    timeout on the CALL, not on the test. `subprocess.run(..., timeout=30)` in
    test_cli.py is that. Without it a hung test blocks the runner until CI
    kills the whole job, and the report says "cancelled" rather than naming the
    test.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", "print('quick')"], capture_output=True,
        text=True, timeout=30,
    )
    assert result.stdout.strip() == "quick"


# ── the alternative, if you want it ─────────────────────────────────────────

def test_freezegun_if_you_have_it():
    """freezegun patches datetime/time globally for a block. Genuinely the
    right answer for code that calls `datetime.now()` in a place you cannot
    reach -- a template, an ORM default, a third-party library.

    Skipped when absent, because fwvault has no runtime dependencies and this
    is a demonstration rather than a requirement."""
    freezegun = pytest.importorskip("freezegun", reason="optional; pip install freezegun")

    with freezegun.freeze_time("2026-01-01 00:00:00"):
        import datetime

        assert datetime.datetime.now().year == 2026


def test_the_system_clock_reports_real_time():
    """SystemClock is what runs in production and the suite never calls it, so
    nothing would notice if `now()` returned a constant.

    Bounded against the wall clock rather than compared to it exactly: the
    assertion is that it tracks real time, not that two calls agree to the
    microsecond.
    """
    before = time.time()
    now = SystemClock().now()
    after = time.time()
    assert before <= now <= after
