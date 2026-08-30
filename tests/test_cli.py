"""Two ways to test a command line, and why you want both.

    in-process    main(["inspect", path]) with capsys. Microseconds. Every
                  branch. Real tracebacks. This is where the coverage lives.
    subprocess    python -m fwvault ... . Milliseconds each. A handful of
                  cases. This is where "works on my machine" goes to die.

The in-process tests are only possible because `main` takes argv, returns an
int, and writes to streams it was handed. That shape costs nothing and is the
single highest-leverage decision in a CLI's design -- a main() that reads
sys.argv and calls sys.exit can only be tested by launching a process.

But in-process tests cannot see: whether the package is importable from a
clean interpreter, whether the console entry point exists, what the shell sees
as the exit code, or anything about stream buffering. Those need a real
process, and four of them is enough.

`capsys` captures at the Python level (sys.stdout/sys.stderr). `capfd`
captures at file-descriptor level, which is what you need when a C extension
or a subprocess writes past Python. Reach for capsys first; if output goes
missing, that is your answer.
"""

import io
import json
import os
import subprocess
import sys

import pytest

from fwvault import cli
from fwvault.signing import Response
from fwvault.testing import (
    RecordingTransport,
    UNKNOWN_FAMILY,
    build_uf2,
    signed_body,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def artifact(tmp_path):
    path = tmp_path / "fw.uf2"
    path.write_bytes(build_uf2(blocks=2))
    return str(path)


def run(argv, transport=None):
    """In-process. Returns (code, stdout, stderr) with streams we own.

    Passing explicit StringIOs rather than using capsys keeps the two
    independent: capsys also captures pytest's own output and anything a
    library logs, which makes an exact-match assertion on stdout fragile."""
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(argv, stdout=out, stderr=err, transport=transport)
    return code, out.getvalue(), err.getvalue()


# ── exit codes are a contract ───────────────────────────────────────────────

def test_inspect_exits_zero(artifact):
    code, out, _err = run(["inspect", artifact])
    assert code == cli.EXIT_OK
    assert "uf2 1024 bytes" in out


def test_a_missing_file_is_exit_one(tmp_path):
    code, _out, err = run(["inspect", str(tmp_path / "nope.uf2")])
    assert code == cli.EXIT_ERROR
    assert "cannot read" in err


def test_bad_usage_is_exit_two(capsys):
    """argparse writes to the real stderr and raises SystemExit; main catches
    it and returns the code. capsys is used here rather than our StringIOs
    precisely because argparse bypasses them."""
    code = cli.main(["nosuchcommand"])
    assert code == cli.EXIT_USAGE
    assert "invalid choice" in capsys.readouterr().err


def test_a_malformed_artifact_is_exit_four(tmp_path):
    path = tmp_path / "bad.uf2"
    path.write_bytes(build_uf2(blocks=2, bad_end_magic=1))
    code, _out, err = run(["inspect", str(path)])
    assert code == cli.EXIT_MALFORMED
    assert "bad end magic" in err


def test_a_policy_rejection_is_exit_three(tmp_path):
    path = tmp_path / "odd.uf2"
    path.write_bytes(build_uf2(blocks=1, family=UNKNOWN_FAMILY))
    code, _out, err = run(["check", str(path), "--allow-unsigned"])
    assert code == cli.EXIT_REJECTED
    assert "UNKNOWN_FAMILY" in err


def test_an_oracle_outage_is_exit_five(artifact):
    """A distinct code, because a build script must be able to tell "your
    firmware is bad" from "our infrastructure is down". One exit code for both
    means a red build teaches nobody anything."""
    from fwvault.signing import TransportError
    from fwvault.testing import ScriptedTransport

    dead = ScriptedTransport([TransportError("down")] * 3)
    code, _out, err = run(
        ["check", artifact, "--oracle", "https://oracle.example.com"], transport=dead
    )
    assert code == cli.EXIT_UNAVAILABLE
    assert "oracle unavailable" in err


def test_every_exit_code_is_distinct():
    """Trivial, and it catches the copy-paste that gives two failure modes the
    same number."""
    codes = [cli.EXIT_OK, cli.EXIT_ERROR, cli.EXIT_USAGE,
             cli.EXIT_REJECTED, cli.EXIT_MALFORMED, cli.EXIT_UNAVAILABLE]
    assert len(set(codes)) == len(codes)


# ── output ──────────────────────────────────────────────────────────────────

def test_json_output_is_parseable(artifact):
    code, out, _err = run(["--json", "inspect", artifact])
    assert code == 0
    assert json.loads(out)["family"] == "RP2040"


def test_findings_go_to_stderr_and_data_to_stdout(tmp_path):
    """So `fwvault --json inspect x | jq` works while warnings are still
    visible in the terminal. Mixing them means the pipe eats the warnings or
    the JSON parse fails -- and which one it is depends on the day."""
    path = tmp_path / "warn.uf2"
    path.write_bytes(build_uf2(blocks=3, wrong_num_blocks=9))
    _code, out, err = run(["--json", "inspect", str(path)])

    json.loads(out)                              # stdout is pure JSON
    assert "warning:" in err


def test_check_accepts_a_signed_artifact(artifact):
    transport = RecordingTransport(routes={"": Response(200, signed_body())})
    code, out, _err = run(
        ["check", artifact, "--oracle", "https://oracle.example.com"], transport=transport
    )
    assert (code, out.strip()) == (cli.EXIT_OK, "accepted")


def test_ingest_writes_to_the_vault(artifact, tmp_path):
    vault = tmp_path / "vault"
    code, out, _err = run(["ingest", artifact, "--vault", str(vault)])
    assert code == cli.EXIT_OK
    assert out.startswith("stored ")
    assert vault.exists()


def test_ingest_is_idempotent(artifact, tmp_path):
    vault = str(tmp_path / "vault")
    run(["ingest", artifact, "--vault", vault])
    _code, out, _err = run(["ingest", artifact, "--vault", vault])
    assert out.startswith("already present ")


# ── the parser surface ──────────────────────────────────────────────────────

def test_every_subcommand_has_help_text():
    """The cheapest documentation test there is: walk the parser and assert
    each action carries help. A flag with no help is a flag nobody can use, and
    it is invisible to every other test in this file."""
    parser = cli.build_parser()
    subparsers = [
        action for action in parser._actions
        if hasattr(action, "choices") and isinstance(action.choices, dict)
    ]
    assert subparsers, "no subcommands found; did the parser shape change?"

    missing = []
    for action in subparsers:
        for name, sub in action.choices.items():
            for arg in sub._actions:
                if arg.dest != "help" and not arg.help:
                    missing.append("{} {}".format(name, arg.dest))
    assert not missing, "undocumented flags: " + ", ".join(missing)


# ── the real process ────────────────────────────────────────────────────────

def _module_run(args, **kwargs):
    env = dict(os.environ, PYTHONPATH=os.path.join(REPO, "src"))
    return subprocess.run(
        [sys.executable, "-m", "fwvault"] + args,
        capture_output=True, text=True, env=env, cwd=REPO, timeout=30, **kwargs
    )


def test_the_module_is_runnable_from_a_clean_interpreter(artifact):
    """The one thing no in-process test can tell you: that `python -m fwvault`
    works at all. An import error in __main__.py, a missing __init__ export, a
    circular import that only bites on a cold start -- all invisible to a test
    running inside an interpreter that already imported everything."""
    result = _module_run(["inspect", artifact])
    assert result.returncode == 0, result.stderr
    assert "uf2 1024 bytes" in result.stdout


def test_the_shell_sees_the_exit_code(tmp_path):
    """returncode as the OS reports it, not as main() returned it. sys.exit
    with a non-int, an uncaught exception, or an atexit handler that raises all
    break this while every in-process test stays green."""
    path = tmp_path / "bad.uf2"
    path.write_bytes(b"\x00" * 64)
    assert _module_run(["inspect", str(path)]).returncode == cli.EXIT_MALFORMED


def test_stdout_stays_parseable_through_a_real_pipe(artifact):
    """Buffering, encoding, and line endings are process-level facts. This is
    the test that catches a stray print() somewhere in the import path -- which
    corrupts the JSON for every downstream consumer and is completely invisible
    to capsys."""
    result = _module_run(["--json", "inspect", artifact])
    assert json.loads(result.stdout)["kind"] == "uf2"


def test_no_arguments_is_a_usage_error():
    result = _module_run([])
    assert result.returncode == cli.EXIT_USAGE
    assert "usage:" in result.stderr


def test_ingest_refuses_a_rejected_artifact_and_stores_nothing(tmp_path):
    """The `ingest` rejection path, which a coverage pass found untested: the
    `check` verb had a test and the verb that actually writes did not.

    The assertion that matters is the second one. Exit 3 without an empty vault
    would mean the service reported a refusal and kept the file anyway.
    """
    path = tmp_path / "odd.uf2"
    path.write_bytes(build_uf2(blocks=1, family=UNKNOWN_FAMILY))
    vault = tmp_path / "vault"

    code, out, err = run(["ingest", str(path), "--vault", str(vault)])

    assert code == cli.EXIT_REJECTED
    assert "UNKNOWN_FAMILY" in err
    assert out == ""
    assert not any(vault.rglob("*.bin")), "a rejected artifact was stored anyway"
