"""The dependency boundary, asserted two ways: statically and behaviourally.

fwvault's core has no runtime dependencies. That claim is worth exactly as much
as the test that enforces it, because the way it breaks is invisible: someone
adds `import httpx` at the top of signing.py, every test passes on a developer
machine where httpx is installed, and `pip install fwvault` starts failing for
everyone else.

Two independent checks, because either alone has a hole:

    static        walk the AST of every module and assert no module-level
                  import of an optional package. Catches the import before it
                  ever runs. Blind to a lazy import that is unconditionally
                  reached.
    behavioural   make the package unimportable via sys.modules and check the
                  core still works. Catches the lazy import. Blind to a module
                  nothing in the test happens to touch.

The sys.modules trick is the interesting one: setting an entry to None makes
`import x` raise ImportError, so you can test the it-is-not-installed path on a
machine where it is very much installed. The alternative is a second CI job
with a different lockfile, which is real work and gets disabled the first time
it goes red on a Friday.
"""

import ast
import importlib
import os
import subprocess
import sys

import pytest

SRC_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"
)
SRC = os.path.join(SRC_ROOT, "fwvault")

# Everything under [project.optional-dependencies]. A module-level import of
# any of these is the defect.
OPTIONAL = {"httpx", "starlette", "hypothesis", "anyio", "uvicorn", "pytest",
            "requests", "pydantic", "numpy"}

# Modules allowed to import the test stack, because they ARE the test stack.
EXEMPT = set()


def _module_level_imports(path):
    """Top-level imports only. A lazy import inside a function is the contract,
    not a violation -- which is why this walks `tree.body` rather than using
    ast.walk over everything."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def _package_modules():
    for root, _dirs, files in os.walk(SRC):
        if "__pycache__" in root:
            continue
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(root, name)


# ── static ──────────────────────────────────────────────────────────────────

def test_no_module_level_import_of_an_optional_package():
    """Reads source rather than importing it, so it reports EVERY offender in
    one run instead of dying on the first. A test that fails with "fix this,
    then run me again to find the next one" wastes an afternoon."""
    offenders = []
    for path in _package_modules():
        name = os.path.relpath(path, SRC)
        if name in EXEMPT:
            continue
        hits = _module_level_imports(path) & OPTIONAL
        if hits:
            offenders.append("{}: {}".format(name, ", ".join(sorted(hits))))

    assert not offenders, (
        "these import an optional package at module level, which breaks a bare "
        "`pip install fwvault` for everyone who does not already have it. Move "
        "the import inside the function that needs it:\n  " + "\n  ".join(offenders)
    )


def test_the_static_check_can_actually_fail(tmp_path):
    """A detector nobody has seen fire is a detector nobody should trust.

    Writes a module that violates the rule and asserts the checker catches it.
    Without this, `_module_level_imports` returning an empty set for every
    input would make the test above pass forever.
    """
    bad = tmp_path / "bad.py"
    bad.write_text("import httpx\n\n\ndef f():\n    return httpx\n", encoding="utf-8")
    assert _module_level_imports(str(bad)) & OPTIONAL == {"httpx"}


def test_a_lazy_import_is_not_flagged(tmp_path):
    """The complement. A function-level import is the contract, and a checker
    that flags it would push everyone to disable the check."""
    fine = tmp_path / "fine.py"
    fine.write_text("def f():\n    import httpx\n    return httpx\n", encoding="utf-8")
    assert _module_level_imports(str(fine)) & OPTIONAL == set()


# ── behavioural ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("absent", sorted(OPTIONAL), ids=sorted(OPTIONAL))
def test_the_core_imports_with_every_optional_package_missing(absent, monkeypatch):
    """One test per optional package, so a failure names which one broke it.

    The delitem before the setitem is not optional: if the module is already in
    sys.modules, assigning None over an existing entry is what takes effect,
    and forgetting the clear gives a test that passes for the wrong reason.
    """
    monkeypatch.delitem(sys.modules, absent, raising=False)
    monkeypatch.setitem(sys.modules, absent, None)

    for name in ("fwvault", "fwvault.parse", "fwvault.policy", "fwvault.signing",
                 "fwvault.store", "fwvault.app", "fwvault.cli", "fwvault.testing"):
        monkeypatch.delitem(sys.modules, name, raising=False)

    module = importlib.import_module("fwvault")
    assert module.parse is not None


def test_the_whole_pipeline_runs_with_nothing_optional_installed(monkeypatch, tmp_path):
    """Import is not enough -- the code has to WORK. This runs a real ingest
    end to end with every optional package unimportable."""
    for absent in OPTIONAL:
        monkeypatch.delitem(sys.modules, absent, raising=False)
        monkeypatch.setitem(sys.modules, absent, None)

    from fwvault.parse import parse
    from fwvault.policy import evaluate
    from fwvault.signing import Verdict
    from fwvault.store import Manifest, Store, digest_of
    from fwvault.testing import RP2040, build_uf2

    blob = build_uf2(blocks=2, family=RP2040)
    image = parse(blob)
    assert evaluate(image, Verdict(signed=True, signer="ci")) == ()

    store = Store(tmp_path / "vault")
    store.put(blob, Manifest(
        digest=digest_of(blob), kind=image.kind, size=image.size,
        family=image.family, entry=image.entry, signer="ci", warnings=(),
    ))
    assert len(store) == 1


def test_the_asgi_app_needs_no_framework(monkeypatch, tmp_path):
    """The claim in app.py's docstring, enforced. It is an ASGI app, not a
    Starlette app, and it must keep working when Starlette is not there."""
    for absent in ("starlette", "httpx", "uvicorn"):
        monkeypatch.delitem(sys.modules, absent, raising=False)
        monkeypatch.setitem(sys.modules, absent, None)

    for name in list(sys.modules):
        if name.startswith("fwvault"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    app_module = importlib.import_module("fwvault.app")
    store_module = importlib.import_module("fwvault.store")
    app = app_module.create_app(store=store_module.Store(tmp_path / "v"))
    assert callable(app)


# ── the real thing, in a real interpreter ───────────────────────────────────

def test_a_cold_interpreter_can_import_the_package():
    """sys.modules games happen inside a process that already imported
    everything. This is the version that cannot lie: a fresh interpreter, `-I`
    to ignore the user site directory, importing the package from source.

    Catches a circular import that only bites on a cold start, which is
    invisible to every other test in this file."""
    program = (
        "import sys; sys.path.insert(0, {!r}); "
        "import fwvault; print(fwvault.__version__)".format(SRC_ROOT)
    )
    # -I isolates: no user site directory, and -- the part that bites -- no
    # PYTHONPATH either, since -I implies -E. So the path goes in the program
    # rather than the environment. An earlier version of this test passed
    # PYTHONPATH and spent a while looking like a packaging bug.
    result = subprocess.run(
        [sys.executable, "-I", "-c", program],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.3.0"
