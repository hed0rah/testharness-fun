"""Markers, skip, xfail, and what to do about a flaky test.

Four ways a test can not-run, and they mean completely different things:

    skip            this does not apply here          (platform, missing dep)
    skipif(cond)    the same, decided at collection
    xfail           this is BROKEN and we know        (a bug with a ticket)
    xfail(strict)   ...and tell me the moment it stops being broken
    deselected      a marker the run excluded         (-m 'not net')

The one people get wrong is xfail, and the failure mode is quiet. A plain
`xfail` on a test that starts passing reports XPASS and stays green. So the bug
gets fixed, nobody notices, the marker sits there for two years, and the test
has been asserting nothing that whole time. `strict=True` turns that XPASS into
a failure, which is the only setting that makes xfail a temporary state rather
than a permanent one.

Set `xfail_strict = true` in pyproject and you get that by default. This repo
does not, so both behaviours are demonstrable below.

Nothing here is skipped for real. Every "skipped" case is a nested pytest run
inside a temp directory (see `run_pytest`), so the outcomes are ASSERTED rather
than described in a comment nobody checks.
"""

import subprocess
import sys
import textwrap

import pytest

from fwvault.parse import parse
from fwvault.testing import UNKNOWN_FAMILY, build_uf2

pytestmark = pytest.mark.usefixtures("isolate_environment")


def run_pytest(tmp_path, body, *args):
    """Run a throwaway suite and return (returncode, stdout).

    The only honest way to test test-outcomes. Asserting that a skip happened
    from inside the same run means asserting on a thing that, by definition,
    did not execute.
    """
    (tmp_path / "test_nested.py").write_text(
        "import pytest\n\n" + textwrap.dedent(body), encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rA", "-q",
         str(tmp_path / "test_nested.py"), *args],
        capture_output=True, text=True, timeout=120, cwd=str(tmp_path),
    )
    return result.returncode, result.stdout


# ── skip vs xfail ───────────────────────────────────────────────────────────

def test_skip_reports_as_skipped(tmp_path):
    code, out = run_pytest(tmp_path, '''
        def test_not_applicable():
            pytest.skip("no serial port on this host")
    ''')
    assert code == 0
    assert "1 skipped" in out
    assert "no serial port on this host" in out, "the reason must reach the summary"


def test_skipif_is_decided_at_collection(tmp_path):
    code, out = run_pytest(tmp_path, '''
        import sys

        @pytest.mark.skipif(sys.platform == "definitely-not-a-platform",
                            reason="never true")
        def test_runs():
            assert True

        @pytest.mark.skipif(True, reason="always true")
        def test_does_not():
            assert False
    ''')
    assert code == 0
    assert "1 passed" in out and "1 skipped" in out


def test_a_plain_xfail_that_passes_is_silently_green(tmp_path):
    """XPASS, exit code 0, nothing red.

    This is the failure mode. The bug got fixed, the marker stayed, and the
    test has been asserting nothing since. Two years later somebody deletes
    the marker and discovers the test never worked.
    """
    code, out = run_pytest(tmp_path, '''
        @pytest.mark.xfail(reason="known bug, ticket FW-118")
        def test_the_bug_is_fixed_now():
            assert True
    ''')
    assert code == 0
    assert "xpassed" in out.lower() or "XPASS" in out


def test_a_strict_xfail_that_passes_is_a_failure(tmp_path):
    """The setting that makes xfail a temporary state.

    `strict=True` says: I expect this to fail, and if it stops failing I want
    to know immediately so I can delete the marker. That is the only version
    worth using.
    """
    code, out = run_pytest(tmp_path, '''
        @pytest.mark.xfail(strict=True, reason="known bug, ticket FW-118")
        def test_the_bug_is_fixed_now():
            assert True
    ''')
    assert code != 0
    assert "failed" in out.lower()


def test_a_strict_xfail_that_still_fails_is_green(tmp_path):
    """The normal state of a live xfail: the bug is still there, the suite is
    still green, and the marker documents it."""
    code, out = run_pytest(tmp_path, '''
        @pytest.mark.xfail(strict=True, reason="known bug, ticket FW-118")
        def test_still_broken():
            assert False
    ''')
    assert code == 0
    assert "xfailed" in out.lower()


def test_xfail_raises_narrows_it_further(tmp_path):
    """`raises=` means "fails FOR THIS REASON". Without it, an xfail absorbs
    every failure -- including the ImportError you introduced this morning,
    which is not the bug you were documenting."""
    code, out = run_pytest(tmp_path, '''
        @pytest.mark.xfail(strict=True, raises=ValueError, reason="FW-118")
        def test_fails_the_wrong_way():
            raise TypeError("not the documented bug")
    ''')
    assert code != 0


# ── pytest.param: marking ONE case ──────────────────────────────────────────

@pytest.mark.parametrize(
    "family,expected",
    [
        pytest.param(0xE48BFF56, "RP2040", id="rp2040"),
        pytest.param(0xADA52840, "NRF52840", id="nrf52840"),
        pytest.param(
            UNKNOWN_FAMILY, "SOME-FUTURE-CHIP",
            id="unknown",
            marks=pytest.mark.xfail(
                strict=True,
                reason="we do not name unknown families; parse returns None",
            ),
        ),
    ],
)
def test_family_naming_with_one_expected_failure(family, expected):
    """`pytest.param` wraps a single case so it can carry its own id AND its
    own marks.

    The third case is a real, documented gap: an unrecognised family ID gets
    `None`, not a name. Marking it `xfail(strict=True)` says so in the suite
    rather than in a comment, and the day someone adds that family to the
    table this test fails and tells them to delete the marker.
    """
    assert parse(build_uf2(blocks=1, family=family)).family == expected


@pytest.mark.parametrize(
    "blocks",
    [1, 2, pytest.param(600, marks=pytest.mark.slow, id="600-blocks")],
)
def test_marks_can_select_out_one_case(blocks):
    """`pytest -m 'not slow'` drops only the 600-block case. Without
    pytest.param the marker would have to go on the whole function, taking the
    two cheap cases with it."""
    assert parse(build_uf2(blocks=blocks)).block_count == blocks


# ── usefixtures: a fixture with nothing to return ───────────────────────────

@pytest.fixture
def strict_umask():
    """A fixture that changes state and returns nothing useful. Requesting it
    by name in the signature leaves an unused argument that every linter
    flags."""
    return None


@pytest.mark.usefixtures("strict_umask")
def test_usefixtures_avoids_an_unused_argument():
    """For side-effect-only fixtures. The dependency is still declared and
    still visible; it just is not pretending to be a value.

    Do NOT reach for this to hide a fixture whose value you actually want --
    the signature is where a reader looks for a test's inputs.
    """
    assert True


# ── the flaky test ──────────────────────────────────────────────────────────

def test_the_policy_on_flaky_tests_is_written_down():
    """There is no code here. That is deliberate: the answer to a flaky test
    is a policy, not a plugin, and this repo's policy is stated where somebody
    will read it.

        1. a flaky test is a BUG REPORT, against the test or the code.
           it is never noise. something is genuinely non-deterministic.
        2. the usual causes, in the order they actually occur:
             - unseeded randomness            (see tests/test_hostile.py)
             - a real clock or a real sleep   (see tests/test_time.py)
             - shared state between tests     (see tests/test_suite_hygiene.py)
             - a fixed path two workers race  (see tests/test_store.py)
             - a real network call            (see the `net` marker)
             - dict/set ordering assumed
        3. QUARANTINE, do not rerun. move it to a marker that is deselected in
           CI, with a ticket. it stops blocking, and it stops lying.
        4. pytest-rerunfailures is a last resort for a genuinely external
           dependency you do not control. `--reruns 3` on your own code
           converts a real bug into a slower green run, permanently.

    The tell that you have this wrong: anyone on the team has ever said
    "just re-run it".
    """
    assert True, "the docstring is the test"


def test_the_deterministic_alternative_to_a_rerun(clock):
    """What a retry test looks like when the non-determinism is injected
    instead of endured. Zero wall-clock time, exact schedule, same answer
    every run, on every machine."""
    from fwvault.signing import Response, SigningClient
    from fwvault.testing import ScriptedTransport, flaky, signed_body

    script = ScriptedTransport(flaky(2, Response(200, signed_body())))
    client = SigningClient("https://x", transport=script, clock=clock, retries=3)

    assert client.verify("a" * 64).signed is True
    assert clock.slept == [0.5, 1.0]
