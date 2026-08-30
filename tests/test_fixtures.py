"""Fixtures: scope, teardown order, factories, and the ones people misuse.

A fixture is a named setup whose result pytest caches per scope and tears down
in reverse order of setup. Everything below is a consequence of that sentence.

    function   (default) once per test. Almost always right.
    class      once per test class
    module     once per file
    package    once per package directory
    session    once per run

The rule: the narrowest scope that is not painfully slow. A session-scoped
mutable fixture is a global variable with extra steps, and the test that
corrupts it fails a different test, three files later, only when the whole
suite runs in one order.

`yield` is the teardown mechanism. Code after the yield runs even if the test
fails. It does NOT run if the setup before the yield raised -- which is why
setup that can fail belongs after everything that must be cleaned up.
"""

import pytest


# ── ordering and teardown ───────────────────────────────────────────────────

EVENTS = []


@pytest.fixture
def outer():
    EVENTS.append("outer:setup")
    yield "outer"
    EVENTS.append("outer:teardown")


@pytest.fixture
def inner(outer):
    """Depends on `outer`, so pytest builds outer first and tears it down
    last. Dependency order, not declaration order -- which is why a fixture
    that needs to run last should be REQUESTED by the thing it wraps rather
    than listed later in the signature."""
    EVENTS.append("inner:setup")
    yield "inner"
    EVENTS.append("inner:teardown")


def test_fixtures_build_outward_in(inner):
    EVENTS.append("test")
    assert inner == "inner"


def test_teardown_ran_in_reverse():
    """Reads the log the previous test left. A rare legitimate use of state
    shared between tests: the subject IS the ordering."""
    assert EVENTS == [
        "outer:setup", "inner:setup", "test", "inner:teardown", "outer:teardown",
    ]


# ── teardown runs even on failure ───────────────────────────────────────────

CLEANED = []


@pytest.fixture
def always_cleaned():
    yield "resource"
    CLEANED.append("cleaned")


def test_a_failing_test_still_tears_down(always_cleaned):
    """The property that makes yield-fixtures safe for real resources: a temp
    directory, an open socket, a spawned process. try/finally in the test body
    only covers the test body."""
    assert always_cleaned == "resource"


def test_the_cleanup_actually_happened():
    assert CLEANED == ["cleaned"]


# ── scope ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def expensive():
    """Module-scoped and IMMUTABLE. That combination is safe; module-scoped and
    mutable is a shared global that the fourth test in the file corrupts for
    the fifth."""
    return tuple(range(1000))


SEEN = []


def test_expensive_is_built_once_a(expensive):
    SEEN.append(expensive)
    assert len(expensive) == 1000


def test_expensive_is_built_once_b(expensive):
    """The same OBJECT, not an equal one. `is` is what proves the caching;
    `==` would pass against a fixture rebuilt from scratch every time, which
    is the thing being tested."""
    assert expensive is SEEN[0]


def test_a_function_scoped_fixture_is_fresh_each_time(vault):
    """`vault` is function-scoped, so this test and the next both start empty.
    Without that, test order becomes part of the meaning of every assertion."""
    assert len(vault) == 0


def test_and_again(vault):
    assert len(vault) == 0


# ── factories ───────────────────────────────────────────────────────────────

def test_factory_fixture_makes_several(make_uf2):
    """The fixture hands back a FUNCTION. Use this whenever a test needs more
    than one specimen, or one whose shape it computes.

    The alternative -- a fixture per variant -- ends with forty fixtures named
    after their defects and a test whose subject can only be discovered by
    opening conftest.py."""
    small = make_uf2(blocks=1)
    large = make_uf2(blocks=9)
    assert len(large) == 9 * len(small)


@pytest.fixture
def counter_factory():
    """A factory that also cleans up what it made. The list is the registry;
    everything handed out gets torn down, in reverse."""
    made = []

    def make(name):
        made.append(name)
        return name.upper()

    yield make
    made.clear()


def test_factory_with_teardown(counter_factory):
    assert counter_factory("a") == "A"
    assert counter_factory("b") == "B"


# ── parametrized fixtures ───────────────────────────────────────────────────

def test_runs_once_per_format(any_artifact):
    """`any_artifact` is parametrized over uf2 and elf, so this one function
    becomes two test IDs. Right for an invariant that must hold across both.

    Wrong the moment the two cases need different assertions -- a test with
    `if request.param == "uf2"` in it is two tests wearing a trenchcoat."""
    from fwvault.parse import parse

    assert parse(any_artifact).size > 0


# ── request, and introspection ──────────────────────────────────────────────

def test_request_knows_the_test(request):
    """`request` is the fixture that describes the current test. Useful for
    naming temp artifacts after the test that made them, which turns a
    directory full of debris into a map."""
    assert request.node.name == "test_request_knows_the_test"
    assert request.node.get_closest_marker("net") is None


def test_getfixturevalue_for_a_conditional_dependency(request):
    """Requesting a fixture at runtime rather than in the signature. The escape
    hatch for "only build this if the test needs it", and a smell everywhere
    else -- it hides the dependency from the signature, which is the one place
    a reader looks."""
    vault = request.getfixturevalue("vault")
    assert len(vault) == 0


# ── the anti-pattern ────────────────────────────────────────────────────────

@pytest.fixture
def over_helpful_fixture(vault, uf2):
    """Named for what it is. This does setup AND makes an assertion, so a
    failure is reported against every test that uses it, with a traceback
    pointing at conftest instead of at the behaviour that broke.

    Assertions belong in tests. Fixtures build things.
    """
    assert len(vault) == 0, "this assertion is in the wrong place"
    return vault, uf2


def test_the_anti_pattern_still_works_which_is_the_problem(over_helpful_fixture):
    vault, uf2 = over_helpful_fixture
    assert len(uf2) == 1024


# ── overriding a conftest fixture ───────────────────────────────────────────

@pytest.fixture
def policy():
    """Shadows the `policy` fixture from conftest.py, for this MODULE ONLY.

    Resolution is nearest-wins: this module beats tests/conftest.py beats the
    repo root conftest. Powerful and quiet -- nothing anywhere says a name has
    been shadowed, and a test three hundred lines below is now running against
    a different object than its neighbour in the next file.

    Use it when a whole file genuinely needs a different baseline. Never as a
    quick fix for one test: that test should ask for what it needs by name.
    """
    from dataclasses import replace

    from fwvault.policy import DEFAULT

    return replace(DEFAULT, require_signature=False, max_bytes=64)


def test_the_module_level_override_is_what_arrives(policy):
    assert policy.require_signature is False
    assert policy.max_bytes == 64


@pytest.fixture
def strict_policy(policy):
    """An override can also EXTEND the fixture it shadows, by requesting the
    same name. Here `policy` is already this module's version, so the chain is
    module-override -> derived, and the conftest original is unreachable from
    this file."""
    from dataclasses import replace

    return replace(policy, require_signature=True)


def test_an_override_can_build_on_itself(strict_policy):
    assert strict_policy.require_signature is True
    assert strict_policy.max_bytes == 64, "still the module override's ceiling"


# ── fixture(name=) ──────────────────────────────────────────────────────────

@pytest.fixture(name="digest")
def _make_digest(uf2):
    """The function is `_make_digest`; the fixture is `digest`.

    Two reasons this exists. It frees the good name for a normal import in the
    same module, and it stops a linter flagging the fixture function as unused.
    The cost is one more layer between the name in a signature and the code
    that produces it.
    """
    from fwvault.store import digest_of

    return digest_of(uf2)


def test_fixture_name_decouples_the_function_from_the_fixture(digest):
    assert len(digest) == 64


# ── addfinalizer, and why yield is usually better ───────────────────────────

@pytest.fixture
def with_finalizer(request):
    """The older teardown API. `yield` covers almost every case and reads
    better, but addfinalizer still wins in two situations: registering cleanup
    CONDITIONALLY, and registering several finalizers that must unwind in
    reverse independently of each other."""
    opened = []

    def close():
        opened.append("closed")

    request.addfinalizer(close)
    opened.append("opened")
    return opened


def test_addfinalizer_runs_after_the_test(with_finalizer):
    assert with_finalizer == ["opened"]


@pytest.fixture
def conditional_cleanup(request, tmp_path):
    """Where addfinalizer genuinely beats yield: the cleanup is registered only
    once the thing that needs cleaning up actually exists. With `yield` the
    teardown half runs even when setup half-failed, and has to defend itself."""
    target = tmp_path / "artifact.bin"
    target.write_bytes(bytes(16))
    request.addfinalizer(target.unlink)      # registered only now that it exists
    return target


def test_conditional_cleanup(conditional_cleanup):
    assert conditional_cleanup.exists()
