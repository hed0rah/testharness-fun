"""Shared fixtures, and the three jobs a conftest actually has.

  1. isolate the process, once, for every test (the autouse fixture below)
  2. hand out specimens and collaborators (the rest of the fixtures)
  3. extend pytest itself (addoption, collection_modifyitems, the marker gate)

conftest.py is not "the file where fixtures go". It is a plugin that pytest
loads by directory, and everything in it applies to that directory and below.
Two consequences people trip on: a fixture defined here needs no import in a
test file, and a conftest deeper in the tree shadows this one for its subtree.

Nothing here reads the developer's real environment, real home directory, or
the network. That is the property that makes a green run locally mean anything
about a green run on a machine you have never seen.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from fwvault import policy as policy_mod              # noqa: E402
from fwvault.app import create_app                    # noqa: E402
from fwvault.clock import FakeClock                   # noqa: E402
from fwvault.signing import Response, SigningClient   # noqa: E402
from fwvault.store import Store                       # noqa: E402
from fwvault.testing import (                         # noqa: E402
    RP2040,
    RecordingTransport,
    build_elf,
    build_uf2,
    signed_body,
)


# ── extending pytest ────────────────────────────────────────────────────────

def pytest_addoption(parser):
    """A flag of our own. Tests that would touch a real network are marked
    `net` and deselected by default; --runnet opts in."""
    parser.addoption(
        "--runnet", action="store_true", default=False,
        help="run tests marked `net`, which make real outbound connections",
    )


def pytest_collection_modifyitems(config, items):
    """Runs after collection, before the first test. This is where a marker
    becomes behaviour.

    The skip carries a REASON, and pyproject sets `-rs`, so a deselected test
    says why in the summary. A silent skip is indistinguishable from a test
    that does not exist, which is how suites quietly shrink.
    """
    if config.getoption("--runnet"):
        return
    skip_net = pytest.mark.skip(reason="needs a real network; pass --runnet")
    for item in items:
        if "net" in item.keywords:
            item.add_marker(skip_net)


# ── isolation ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch, tmp_path_factory):
    """Applied to every test in the tree, whether it asks for it or not.

    autouse is the right call for exactly this: process-wide state that any
    test could touch by accident and no test should have to remember. Using it
    for anything a test could reasonably want to opt out of is how you get a
    suite where nobody can explain what a test is actually running against.

    Deleting the env vars is not enough and was in fact the bug once: with
    FWVAULT_HOME unset the package falls back to expanduser("~"), so the suite
    wrote artifacts into a real home directory. A fake HOME is what contains
    it, and both HOME and USERPROFILE have to be set because expanduser reads
    the former on POSIX and the latter on Windows.
    """
    home = tmp_path_factory.mktemp("fwvault_home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("FWVAULT_HOME", str(home))
    # A walker bug degrades to a warning in production. In here it is the
    # traceback we came for. See parse._walker_raises.
    monkeypatch.setenv("FWVAULT_WALKER_RAISE", "1")
    monkeypatch.delenv("FWVAULT_ORACLE", raising=False)


# ── specimens ───────────────────────────────────────────────────────────────

@pytest.fixture
def uf2():
    """The boring, valid specimen. Every suite needs one, and it should be the
    smallest thing that is genuinely valid -- two blocks, not two hundred."""
    return build_uf2(blocks=2)


@pytest.fixture
def elf():
    return build_elf()


@pytest.fixture
def make_uf2():
    """A factory fixture: the test gets the FUNCTION, not a value.

    Use this whenever a test needs more than one specimen, or a specimen whose
    shape depends on something the test computes. The alternative -- a fixture
    per variant -- ends with forty fixtures named after their defects, and a
    test whose subject is only discoverable by reading a different file.
    """
    return build_uf2


@pytest.fixture(params=["uf2", "elf"], ids=["uf2", "elf"])
def any_artifact(request):
    """A parametrized fixture. Every test that requests it runs twice, once per
    param, and pytest reports them as separate test IDs.

    This is the tool for invariants that must hold across formats. It is the
    wrong tool when the two cases need different assertions -- a test with
    `if request.param == "uf2"` in it is two tests wearing a trenchcoat.
    """
    return build_uf2(blocks=2) if request.param == "uf2" else build_elf()


# ── collaborators ───────────────────────────────────────────────────────────

@pytest.fixture
def vault(tmp_path):
    """A Store rooted in this test's own directory.

    tmp_path is function-scoped and unique per test, so two tests can both
    store the same digest without seeing each other. It also survives the run
    (pytest keeps the last three) which is what you want at 2am when a
    failure is about the bytes on disk.
    """
    return Store(tmp_path / "vault")


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def oracle():
    """A transport that says yes to everything and remembers being asked."""
    return RecordingTransport(routes={"": Response(200, signed_body())})


@pytest.fixture
def client(oracle, clock):
    return SigningClient("https://oracle.example.com", transport=oracle, clock=clock)


@pytest.fixture
def policy():
    """A copy, so a test that mutates it cannot reach the next test. Policy is
    frozen, so this is belt and braces -- but the fixture is the right place to
    make the guarantee, because the next collaborator added here will not be
    frozen and nobody will remember."""
    from dataclasses import replace

    return replace(policy_mod.DEFAULT)


@pytest.fixture
def app(vault, client, policy):
    """The whole service, wired to fakes. One line, because every collaborator
    is a parameter -- see app.create_app."""
    return create_app(store=vault, client=client, policy=policy)


@pytest.fixture
def signed_uf2(uf2):
    """A specimen the default policy accepts. Named for what it IS to the
    policy, not for how it was built."""
    assert build_uf2(blocks=2, family=RP2040) == uf2
    return uf2
