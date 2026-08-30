"""Parametrization past the basics: indirect, generate_tests, and stacking.

`@pytest.mark.parametrize` handles most cases. The three tools here are for
when it does not:

    indirect=True          the param goes to a FIXTURE, not to the test, so
                           each case gets setup and teardown
    pytest_generate_tests  build the case list at collection time, from
                           something you cannot write as a literal
    fixture(params=)       every test requesting the fixture runs once per case

Reach for them in that order, and only when a plain parametrize will not do.
All three move the case list further from the test that uses it, and that is a
real cost: the failure `test_thing[case-7]` is only useful if the reader can
find what case 7 is.
"""

import pytest

from fwvault.parse import UF2_BLOCK_SIZE, parse
from fwvault.policy import DEFAULT, evaluate
from fwvault.signing import Verdict
from fwvault.testing import NRF52840, RP2040, UNKNOWN_FAMILY, build_elf, build_uf2

SIGNED = Verdict(signed=True, signer="ci-builder", key_id="k-2f81")


# ── indirect: the param goes to the fixture ─────────────────────────────────

@pytest.fixture
def artifact(request):
    """Receives the parametrize value as `request.param` and turns it into a
    real specimen. The test never sees the raw parameter."""
    kind, count = request.param
    blob = build_uf2(blocks=count) if kind == "uf2" else build_elf()
    return parse(blob)


@pytest.mark.parametrize(
    "artifact,expected_blocks",
    [
        (("uf2", 1), 1),
        (("uf2", 7), 7),
        (("elf", 0), 1),
    ],
    indirect=["artifact"],
    ids=["uf2-1", "uf2-7", "elf"],
)
def test_indirect_parametrization(artifact, expected_blocks):
    """`indirect=["artifact"]` names WHICH parameters get routed through a
    fixture. The other one, `expected_blocks`, arrives normally.

    Worth it when each case needs setup or teardown: a temp directory per
    case, an open file, a spawned process. Not worth it when the fixture is
    just a function call, which is what a factory fixture is for.
    """
    assert artifact.block_count == expected_blocks


@pytest.fixture
def vault_with(request, tmp_path):
    """Indirect earning its keep: real setup AND real teardown per case."""
    from fwvault.store import Manifest, Store, digest_of

    store = Store(tmp_path / "v")
    store.expected = request.param       # so the test can assert without re-deriving
    for n in range(1, request.param + 1):
        blob = build_uf2(blocks=n, family=RP2040)
        image = parse(blob)
        store.put(blob, Manifest(
            digest=digest_of(blob), kind=image.kind, size=image.size,
            family=image.family, entry=image.entry, signer=None, warnings=(),
        ))
    yield store
    # teardown a plain parametrize cannot express: tmp_path handles the files,
    # this is where a socket, a process or a database transaction would close.


@pytest.mark.parametrize("vault_with", [0, 1, 5], indirect=True,
                         ids=lambda n: "%d-stored" % n)
def test_vault_size(vault_with):
    """Three vaults, three sizes, one test. Each case built and torn down by
    the fixture, which is the thing a plain parametrize cannot do."""
    assert len(vault_with) == vault_with.expected


# ── pytest_generate_tests: build the list at collection ─────────────────────

def pytest_generate_tests(metafunc):
    """The hook behind parametrize. Runs once per test function, at collection.

    Use it when the case list cannot be a literal: read from a directory of
    specimens, derive from an enum, expand a matrix from a config file. Here
    it derives the cases from the package's own family table, so adding a
    supported chip automatically adds a test and nobody has to remember.
    """
    if "known_family" in metafunc.fixturenames:
        import importlib

        families = importlib.import_module("fwvault.parse").FAMILIES
        metafunc.parametrize(
            "known_family,expected_name",
            sorted(families.items()),
            ids=[name.lower() for _fid, name in sorted(families.items())],
        )


def test_every_family_in_the_table_is_named(known_family, expected_name):
    """Five tests, and the list came from the source of truth rather than
    from a copy of it in this file.

    The tradeoff: `pytest --collect-only` still shows the ids, but a reader
    of this file cannot see the cases without running that command. Pay it
    only when keeping a literal list in sync is the bigger risk.
    """
    assert parse(build_uf2(blocks=1, family=known_family)).family == expected_name


# ── stacking, and the size of the product ───────────────────────────────────

@pytest.mark.parametrize("blocks", [1, 3], ids=lambda n: "%db" % n)
@pytest.mark.parametrize("payload", [0, 476], ids=lambda n: "%dp" % n)
@pytest.mark.parametrize("family", [RP2040, NRF52840], ids=["rp2040", "nrf"])
def test_stacked_parametrize_is_a_product(blocks, payload, family):
    """2 x 2 x 2 = 8 tests from three lines, ids composed as
    `[rp2040-0p-1b]`.

    The warning: this multiplies. A fourth axis of 5 values is 40 tests, and
    a fifth is 200. When the product stops being meaningful -- when most
    combinations test nothing new -- switch to a hand-picked list of the
    combinations that matter, or to property-based testing, which searches the
    space instead of enumerating it.
    """
    image = parse(build_uf2(blocks=blocks, payload_size=payload, family=family))
    assert image.size == blocks * UF2_BLOCK_SIZE
    assert image.payload_bytes == blocks * payload


# ── parametrizing the policy, which is the real use ─────────────────────────

@pytest.mark.parametrize(
    "specimen,verdict,expected",
    [
        pytest.param(dict(blocks=2, family=RP2040), SIGNED, [], id="accepted"),
        pytest.param(dict(blocks=1, family=UNKNOWN_FAMILY), SIGNED,
                     ["UNKNOWN_FAMILY"], id="unknown-family"),
        pytest.param(dict(blocks=2, family=RP2040), Verdict(signed=False),
                     ["UNSIGNED"], id="unsigned"),
        pytest.param(dict(blocks=1, family=RP2040, payload_size=0), SIGNED,
                     ["EMPTY_PAYLOAD"], id="empty"),
    ],
)
def test_policy_table(specimen, verdict, expected):
    """A policy is a table, so test it as one. Each row is a named case, the
    accepting row is first, and a new rule is a new row.

    This is the shape to reach for before writing four near-identical test
    functions -- but only while the assertion stays identical. The moment one
    row needs a different assertion, it becomes its own test.
    """
    image = parse(build_uf2(**specimen))
    assert [r.code for r in evaluate(image, verdict, DEFAULT)] == expected
