"""Time as a dependency rather than an ambient fact.

Every retry loop, cache expiry and timestamp in this package goes through a
Clock. That is not ceremony: it is the difference between a test that sleeps
three seconds and a test that asserts the backoff schedule was 0.5s, 1.0s,
2.0s and returns instantly.

You can also monkeypatch `time.sleep`, and tests/test_time.py does exactly that
to show the technique. Injection is still better -- it survives the module
being imported under a different name, it does not leak into unrelated code
running in the same process, and the fake can be interrogated afterwards.
"""

import time


class SystemClock:
    """The real one."""

    def now(self):
        return time.time()

    def sleep(self, seconds):
        time.sleep(seconds)


class FakeClock:
    """A clock that only moves when you move it, and remembers being asked to.

    Not a mock: it has real behaviour (now() advances by the amount slept) and
    real state you can assert on. See tests/test_doubles.py for why that
    distinction earns its own word.
    """

    def __init__(self, start=1_700_000_000.0):
        self.t = float(start)
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds

    def advance(self, seconds):
        self.t += seconds
