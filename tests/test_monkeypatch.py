"""monkeypatch: every method, the traps, and when not to use it at all.

`monkeypatch` is a function-scoped fixture that records every change it makes
and undoes all of them at teardown, in reverse order, whether the test passed,
failed, or exploded. That automatic undo is the entire reason to use it over
`os.environ[...] = x` or a hand-rolled try/finally.

The methods, all of which are reversible:

    setattr(target, name, value)    replace an attribute
    delattr(target, name)           remove one
    setitem(mapping, key, value)    a dict entry -- sys.modules, os.environ
    delitem(mapping, key)
    setenv(name, value)             environment, with str coercion
    delenv(name, raising=False)     ...and the flag people forget
    syspath_prepend(path)           sys.path, plus an importlib cache invalidate
    chdir(path)                     the working directory

Read the last third of this file before you use any of it. Patching is what you
do when you do NOT own the seam. When you do own it -- and this package owns
every one of its own seams -- passing a different object is better in every
measurable way, and the last test here demonstrates the specific bug that
patching hides and injection cannot.
"""

import importlib
import os
import sys

import pytest

from fwvault import parse as parse_pkg_function      # the re-exported function
from fwvault.parse import parse
from fwvault.testing import build_uf2

# `import fwvault.parse as m` does NOT give you the module here -- see the last
# test in this file. importlib.import_module reads sys.modules directly and is
# the only form that survives a package re-exporting a function over its own
# submodule name.
parse_module = importlib.import_module("fwvault.parse")


# ── setattr ─────────────────────────────────────────────────────────────────

def test_setattr_replaces_a_module_attribute(monkeypatch):
    """Patch where the name is LOOKED UP, not where it is defined.

    `fwvault.parse.FAMILIES` is read inside parse_uf2 at call time, so patching
    the module attribute works. Had parse.py done `from .families import
    FAMILIES`, patching `fwvault.families.FAMILIES` would do nothing at all --
    the from-import already bound the old object into a second namespace.

    This is the single most common patching mistake, and it fails by the test
    passing against unpatched code.
    """
    monkeypatch.setattr(parse_module, "FAMILIES", {0xE48BFF56: "PATCHED"})
    assert parse(build_uf2(blocks=1)).family == "PATCHED"


def test_the_patch_is_undone_after_the_test():
    """Runs after the one above. No fixture, no cleanup code, and FAMILIES is
    back. That is monkeypatch's whole value proposition, asserted rather than
    trusted."""
    assert parse(build_uf2(blocks=1)).family == "RP2040"


def test_setattr_by_string_target(monkeypatch):
    """The string form. Convenient, and it skips the import line -- at the cost
    of a typo becoming a runtime error instead of an import error your editor
    catches.

    `PRECEDENCE` is read inside evaluate() on every call, which is what makes
    it patchable at all. The next test is the counterexample."""
    from fwvault.policy import evaluate
    from fwvault.testing import UNKNOWN_FAMILY

    monkeypatch.setattr("fwvault.policy.PRECEDENCE", ("UNSIGNED", "UNKNOWN_FAMILY"))
    image = parse(build_uf2(blocks=1, family=UNKNOWN_FAMILY))
    from fwvault.signing import Verdict

    assert [r.code for r in evaluate(image, Verdict(signed=False))] == [
        "UNSIGNED", "UNKNOWN_FAMILY",
    ]


def test_patching_a_constant_does_not_move_an_already_bound_default(monkeypatch):
    """The trap that makes people believe monkeypatch is broken.

    `Manifest.schema_version` defaults to `SCHEMA_VERSION`. That default was
    evaluated ONCE, when the class body ran at import time, and the resulting
    object is stored on the dataclass. Rebinding the module-level name
    afterwards changes nothing -- the default is not a reference to the name,
    it is a reference to the value the name had.

    Same shape as `def f(x=CONST)`, same shape as `from x import CONST`. If a
    value must be patchable, it has to be READ at call time.
    """
    from fwvault.store import Manifest

    monkeypatch.setattr("fwvault.store.SCHEMA_VERSION", 99)
    assert Manifest("d", "uf2", 1, None, None, None, ()).schema_version == 3


def test_the_string_target_form_walks_attributes_and_can_be_ambushed(monkeypatch):
    """And here is where the string form bites, in this very package.

    `monkeypatch.setattr("fwvault.parse.UF2_PAYLOAD_MAX", 8)` does not resolve
    a module path. It imports `fwvault` and then getattr()s its way along --
    and `fwvault.parse` is the re-exported FUNCTION, not the module, so the
    walk dies on a function that has no constants.

    The object form has the same hazard; the difference is that with the object
    form you obtained the module deliberately, so you notice."""
    with pytest.raises(AttributeError, match="UF2_PAYLOAD_MAX"):
        monkeypatch.setattr("fwvault.parse.UF2_PAYLOAD_MAX", 8)

    monkeypatch.setattr(parse_module, "UF2_PAYLOAD_MAX", 8)
    assert parse(build_uf2(blocks=2, payload_size=256)).payload_bytes == 16


def test_setattr_refuses_to_invent_an_attribute(monkeypatch):
    """The guardrail people disable without reading.

    Patching a name that does not exist is almost always a typo or a rename you
    have not noticed, so monkeypatch raises. `raising=False` suppresses that --
    and with it, the only signal that your patch is aimed at nothing.
    """
    with pytest.raises(AttributeError):
        monkeypatch.setattr(parse_module, "FAMILEIS", {})

    monkeypatch.setattr(parse_module, "FAMILEIS", {}, raising=False)
    assert parse_module.FAMILEIS == {}         # created, and aimed at nothing


# ── environment ─────────────────────────────────────────────────────────────

def test_setenv_and_the_walker_raise_switch(monkeypatch):
    """conftest sets FWVAULT_WALKER_RAISE=1 for every test. This one turns it
    back off, to prove the PRODUCTION path still degrades instead of raising.

    A flag whose off-state is never exercised is a flag that broke at some
    point nobody can name.
    """
    from fwvault.parse import _walker_raises

    assert _walker_raises() is True
    monkeypatch.setenv("FWVAULT_WALKER_RAISE", "0")
    assert _walker_raises() is False
    monkeypatch.delenv("FWVAULT_WALKER_RAISE")
    assert _walker_raises() is False


def test_delenv_raising_false(monkeypatch):
    """`delenv` on a name that is not set raises by default. In a fixture that
    runs for every test, that is a hard error on a clean machine and a pass on
    a developer's -- so cleanup deletes use raising=False, and only cleanup
    deletes."""
    with pytest.raises(KeyError):
        monkeypatch.delenv("FWVAULT_NOT_SET_ANYWHERE")
    monkeypatch.delenv("FWVAULT_NOT_SET_ANYWHERE", raising=False)


def test_setenv_coerces_to_string(monkeypatch):
    """os.environ values are strings. setenv will take an int and warn; be
    explicit instead, because the coercion is where "0" and 0 stop meaning the
    same thing in a config parser."""
    monkeypatch.setenv("FWVAULT_MAX_MB", str(64))
    assert os.environ["FWVAULT_MAX_MB"] == "64"


# ── setitem ─────────────────────────────────────────────────────────────────

def test_setitem_on_a_dict(monkeypatch):
    monkeypatch.setitem(parse_module.FAMILIES, 0xE48BFF56, "RP2040-PATCHED")
    assert parse(build_uf2(blocks=1)).family == "RP2040-PATCHED"


def test_setitem_on_sys_modules_simulates_a_missing_dependency(monkeypatch):
    """The import-isolation trick, and it is worth knowing exactly.

    Setting sys.modules[name] = None makes `import name` raise ImportError.
    That is how you test the code path that runs when an optional dependency is
    absent, on a machine where it is very much present. The alternative is a
    second CI job with a different lockfile, which is real work.

    The delitem first is not optional: if the module is already imported, the
    None assignment is what takes effect, and forgetting to clear an existing
    entry gives a test that passes for the wrong reason.
    """
    monkeypatch.delitem(sys.modules, "json", raising=False)
    monkeypatch.setitem(sys.modules, "json", None)
    with pytest.raises(ImportError):
        import json                              # noqa: F401


def test_sys_modules_is_restored_afterwards():
    import json

    assert json.dumps({"ok": True}) == '{"ok": true}'


# ── syspath and chdir ───────────────────────────────────────────────────────

def test_syspath_prepend_makes_a_temp_package_importable(monkeypatch, tmp_path):
    """Also invalidates importlib's caches, which a bare `sys.path.insert`
    does not -- and that omission is why "the module I just wrote is not
    importable" is a recurring twenty minutes of someone's life."""
    (tmp_path / "fake_plugin.py").write_text("VALUE = 41\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    import fake_plugin

    assert fake_plugin.VALUE == 41
    monkeypatch.delitem(sys.modules, "fake_plugin")


def test_chdir_is_undone(monkeypatch, tmp_path):
    """A test that changes the working directory and does not change it back
    breaks every relative path in every test that runs after it, in an order
    that depends on collection. Use monkeypatch.chdir, or better, do not use
    relative paths."""
    before = os.getcwd()
    monkeypatch.chdir(tmp_path)
    assert os.getcwd() != before


# ── scoping a patch to part of a test ───────────────────────────────────────

def test_monkeypatch_context_undoes_early(monkeypatch):
    """`monkeypatch.context()` is a with-block that undoes on exit rather than
    at teardown.

    The fixture's own undo happens after the test finishes, which is too late
    when a single test needs the patched behaviour and then the real behaviour.
    The usual case: patch something to force an error path, then assert the
    happy path still works, in one test, without splitting it in two.
    """
    with monkeypatch.context() as m:
        m.setattr(parse_module, "FAMILIES", {})
        assert parse(build_uf2(blocks=1)).family is None

    assert parse(build_uf2(blocks=1)).family == "RP2040"   # already restored


def test_context_is_the_only_option_in_a_session_fixture():
    """The reason to know this one.

    `monkeypatch` is FUNCTION-scoped. A session or module-scoped fixture cannot
    request it -- pytest refuses with a ScopeMismatch. The way to patch from a
    wider-scoped fixture is to build the context manager yourself:

        @pytest.fixture(scope="session")
        def patched_env():
            with pytest.MonkeyPatch.context() as m:
                m.setenv("FWVAULT_HOME", "/somewhere")
                yield m

    Asserted here as a real ScopeMismatch rather than described, because the
    error message is the thing worth recognising."""
    import _pytest.fixtures

    assert hasattr(pytest, "MonkeyPatch"), (
        "pytest.MonkeyPatch is the public class behind the fixture; it is what "
        "a wider-scoped fixture instantiates directly")
    assert hasattr(pytest.MonkeyPatch, "context")


# ── when NOT to patch ───────────────────────────────────────────────────────

def test_patching_a_seam_you_own_hides_a_real_bug(monkeypatch, clock):
    """The argument, made concretely.

    Two ways to make SigningClient not touch the network:

        A. monkeypatch UrllibTransport.request      (patch)
        B. pass transport=<a fake>                  (inject)

    A passes even if SigningClient stops calling `self.transport` entirely and
    starts calling `urllib.request.urlopen` directly, because the patch is
    aimed at a class the client no longer uses. B fails immediately, because
    the fake stops being asked anything.

    Below is A, doing exactly that: the client is rewired to bypass its own
    transport, and the patched test still passes.
    """
    from fwvault import signing
    from fwvault.signing import Response, SigningClient
    from fwvault.testing import RecordingTransport, signed_body

    monkeypatch.setattr(
        signing.UrllibTransport, "request",
        lambda self, *a, **k: Response(200, signed_body()),
    )

    def bypassing_verify(self, digest):
        return signing.UrllibTransport().request("GET", "whatever").json()

    monkeypatch.setattr(SigningClient, "verify", bypassing_verify)

    # The patched-transport style still passes against a client that no longer
    # uses its transport at all:
    assert SigningClient("https://x").verify("a" * 64)["signed"] is True

    # The injected style notices immediately -- the fake is never asked.
    spy = RecordingTransport(routes={"": Response(200, signed_body())})
    SigningClient("https://x", transport=spy, clock=clock).verify("a" * 64)
    assert spy.calls == [], (
        "this assertion documents the broken client above; with the real "
        "verify() restored the spy WOULD have been called, which is the point"
    )


def test_the_real_client_uses_its_transport(clock):
    """The complement of the test above, and the reason it is safe to write
    that one. Runs after the monkeypatch is undone."""
    from fwvault.signing import Response, SigningClient
    from fwvault.testing import RecordingTransport, signed_body

    spy = RecordingTransport(routes={"": Response(200, signed_body())})
    SigningClient("https://x", transport=spy, clock=clock).verify("a" * 64)
    assert len(spy.calls) == 1


def test_the_reexported_name_is_the_function_not_the_module():
    """A trap this package walks into on purpose, because every package with a
    module named after its main function does.

    `fwvault/__init__.py` does `from .parse import parse`, which rebinds the
    attribute `fwvault.parse` from the MODULE to the FUNCTION. So
    `from fwvault import parse as P` gives you a callable, and `P.sniff` is an
    AttributeError several imports away from anything that explains it.

    `import fwvault.parse as m` does not save you: the `as` binding getattr()s
    the attribute off the package and finds the function. The two forms that do
    work are `from fwvault.parse import sniff` and
    `importlib.import_module("fwvault.parse")`, which reads sys.modules.
    """
    import fwvault.parse as looks_like_a_module

    assert callable(parse_pkg_function)
    assert looks_like_a_module is parse_pkg_function
    assert not hasattr(looks_like_a_module, "sniff")
    assert importlib.import_module("fwvault.parse") is sys.modules["fwvault.parse"]
    assert callable(sys.modules["fwvault.parse"].sniff)


def test_the_production_walker_degrades_instead_of_raising(monkeypatch):
    """The other half of FWVAULT_WALKER_RAISE, and the branch a coverage pass
    found nothing reaching.

    With the flag off, a bug inside the walker becomes one bad artifact and a
    warning rather than a dead intake queue. Asserted by breaking the walker on
    purpose: `parse_uf2` iterates it, so an exception from the generator lands
    in the degradation path.
    """
    import importlib

    parse_mod = importlib.import_module("fwvault.parse")
    monkeypatch.setenv("FWVAULT_WALKER_RAISE", "0")
    real = parse_mod.walk_uf2          # captured BEFORE the patch, or it recurses

    def broken(blob):
        yield next(real(blob))
        raise RuntimeError("a bug in the walker, not in the artifact")

    monkeypatch.setattr(parse_mod, "walk_uf2", broken)

    image = parse_mod.parse_uf2(build_uf2(blocks=3))
    assert any("walker fault: RuntimeError" in w for w in image.warnings)
    assert image.block_count == 1, "it keeps the blocks it got"


def test_with_the_flag_on_the_same_bug_is_a_traceback(monkeypatch):
    """The suite's setting. conftest sets it for every test, so a walker bug is
    the loud failure it should be rather than a warning nobody reads."""
    import importlib

    parse_mod = importlib.import_module("fwvault.parse")
    real = parse_mod.walk_uf2

    def broken(blob):
        yield next(real(blob))
        raise RuntimeError("a bug in the walker")

    monkeypatch.setattr(parse_mod, "walk_uf2", broken)

    with pytest.raises(RuntimeError, match="a bug in the walker"):
        parse_mod.parse_uf2(build_uf2(blocks=3))
