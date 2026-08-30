"""The command line, written to be testable two ways at once.

`main(argv)` takes its arguments and returns an exit code. It does not read
sys.argv, does not call sys.exit, and writes to streams it was handed. That one
decision means the fast tests call `main(["inspect", path])` in-process with
capsys and run in microseconds, while tests/test_cli.py ALSO drives the real
`python -m fwvault` through subprocess for the handful of things only a real
process can show: the shebang path, the exit code as the shell sees it, stream
interleaving, and whether the module is importable at all from a clean
interpreter.

Both are needed. The in-process tests are where the coverage lives; the
subprocess tests are where "it works on my machine" goes to die.

Exit codes are a contract. They are listed here, asserted in test_cli.py, and
never renumbered.
"""

import argparse
import json
import sys

from .errors import ParseError, VaultUnavailable
from .parse import parse
from .policy import DEFAULT, evaluate
from .signing import SigningClient
from .store import Manifest, Store, digest_of

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_REJECTED = 3
EXIT_MALFORMED = 4
EXIT_UNAVAILABLE = 5


def build_parser():
    """Split out so a test can introspect the flag surface without running
    anything. test_cli.py walks every subparser and asserts each one has a
    help string, which is the cheapest documentation test there is."""
    parser = argparse.ArgumentParser(
        prog="fwvault", description="firmware artifact intake"
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_inspect = sub.add_parser("inspect", help="parse an artifact and print its header")
    p_inspect.add_argument("path", help="file to inspect")

    p_check = sub.add_parser("check", help="parse and evaluate policy, store nothing")
    p_check.add_argument("path", help="file to check")
    p_check.add_argument("--oracle", help="signing oracle base URL")
    p_check.add_argument(
        "--allow-unsigned", action="store_true", help="do not require a signature"
    )

    p_ingest = sub.add_parser("ingest", help="parse, check policy, store")
    p_ingest.add_argument("path", help="file to ingest")
    p_ingest.add_argument("--vault", default=".fwvault", help="vault root directory")
    p_ingest.add_argument("--oracle", help="signing oracle base URL")

    return parser


def _emit(stream, as_json, payload, human):
    if as_json:
        stream.write(json.dumps(payload, sort_keys=True) + "\n")
    else:
        stream.write(human + "\n")


def main(argv=None, stdout=None, stderr=None, transport=None):
    """Returns an exit code. Never raises for an expected failure.

    `transport` is here for the same reason it is everywhere else in this
    package: so a test can run the real argument parsing, the real dispatch and
    the real output formatting against a signing oracle that is a dict.
    """
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()

    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:                  # argparse exits on bad usage
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE

    try:
        with open(args.path, "rb") as fh:
            blob = fh.read()
    except OSError as exc:
        stderr.write("cannot read {}: {}\n".format(args.path, exc))
        return EXIT_ERROR

    try:
        image = parse(blob)
    except ParseError as exc:
        stderr.write("malformed: {}\n".format(exc))
        return EXIT_MALFORMED

    if args.cmd == "inspect":
        payload = {
            "kind": image.kind,
            "size": image.size,
            "blocks": image.block_count,
            "family": image.family,
            "entry": image.entry,
            "machine": image.machine,
            "warnings": list(image.warnings),
        }
        human = "{} {} bytes, {} block(s), family {}, entry {}".format(
            image.kind, image.size, image.block_count,
            image.family or "unknown",
            hex(image.entry) if image.entry is not None else "?",
        )
        _emit(stdout, args.json, payload, human)
        for warning in image.warnings:
            stderr.write("warning: {}\n".format(warning))
        return EXIT_OK

    verdict = None
    if getattr(args, "oracle", None):
        client = SigningClient(args.oracle, transport=transport)
        try:
            verdict = client.verify(digest_of(blob))
        except VaultUnavailable as exc:
            stderr.write("oracle unavailable: {}\n".format(exc))
            return EXIT_UNAVAILABLE

    policy = DEFAULT
    if getattr(args, "allow_unsigned", False):
        from dataclasses import replace

        policy = replace(DEFAULT, require_signature=False)

    hits = evaluate(image, verdict, policy)

    if args.cmd == "check":
        payload = {"rejections": [{"code": h.code, "detail": h.detail} for h in hits]}
        human = (
            "accepted"
            if not hits
            else "\n".join("{}: {}".format(h.code, h.detail) for h in hits)
        )
        _emit(stdout if not hits else stderr, args.json, payload, human)
        return EXIT_OK if not hits else EXIT_REJECTED

    # ingest
    if hits:
        raise_code = hits[0]
        stderr.write("rejected {}: {}\n".format(raise_code.code, raise_code.detail))
        return EXIT_REJECTED

    store = Store(args.vault)
    digest = digest_of(blob)
    manifest = Manifest(
        digest=digest, kind=image.kind, size=image.size, family=image.family,
        entry=image.entry, signer=verdict.signer if verdict else None,
        warnings=tuple(image.warnings),
    )
    _digest, created = store.put(blob, manifest)
    _emit(
        stdout, args.json,
        {"digest": digest, "created": created},
        "{} {}".format("stored" if created else "already present", digest),
    )
    return EXIT_OK

