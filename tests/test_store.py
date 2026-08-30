"""Filesystem tests: tmp_path, atomicity, idempotency, and path traversal.

`tmp_path` is a `pathlib.Path` to a fresh directory, unique per test, and
pytest keeps the last three runs on disk. That last part is the reason to
prefer it over `tempfile.mkdtemp` -- when something fails at 2am about the
bytes on disk, the bytes are still there.

The scoped variant is `tmp_path_factory` (see conftest's isolation fixture),
which is what you need for anything session-scoped, because `tmp_path` itself
is function-scoped and a session fixture cannot request it.

Never write to a hardcoded path in a test. Not /tmp, not ./out, not
os.getcwd(). Every one of those turns two tests running in parallel into a
race, and `pytest -p xdist -n 4` into a mystery.
"""

import os

import pytest

from fwvault.errors import FwVaultError
from fwvault.parse import parse
from fwvault.store import Manifest, Store, digest_of
from fwvault.testing import build_uf2


def manifest_for(blob):
    image = parse(blob)
    return Manifest(
        digest=digest_of(blob), kind=image.kind, size=image.size,
        family=image.family, entry=image.entry, signer="ci-builder",
        warnings=tuple(image.warnings),
    )


# ── the basics ──────────────────────────────────────────────────────────────

def test_put_then_get_round_trips(vault, uf2):
    digest, created = vault.put(uf2, manifest_for(uf2))
    assert created is True
    assert vault.get(digest) == uf2


def test_the_digest_is_the_key(vault, uf2):
    digest, _created = vault.put(uf2, manifest_for(uf2))
    assert digest == digest_of(uf2)


def test_storing_the_same_bytes_twice_is_a_no_op(vault, uf2):
    vault.put(uf2, manifest_for(uf2))
    _digest, created = vault.put(uf2, manifest_for(uf2))
    assert created is False
    assert len(vault) == 1


def test_different_bytes_are_different_artifacts(vault):
    one = build_uf2(blocks=1)
    two = build_uf2(blocks=2)
    vault.put(one, manifest_for(one))
    vault.put(two, manifest_for(two))
    assert len(vault) == 2


def test_a_manifest_that_describes_other_bytes_is_refused(vault, uf2):
    """The consistency check. Storing bytes under a manifest computed from
    different bytes is how a vault starts serving artifact A under artifact B's
    provenance, and it is a one-line mistake in a caller."""
    with pytest.raises(FwVaultError, match="does not describe these bytes"):
        vault.put(uf2, manifest_for(build_uf2(blocks=5)))


# ── atomicity ───────────────────────────────────────────────────────────────

def test_a_failed_write_leaves_nothing_behind(vault, uf2, monkeypatch):
    """os.replace is the last thing that happens. If the write dies before it,
    the destination path was never created and the temp file is cleaned up.

    Patching os.replace is the right call here: it is not our seam, we do not
    own it, and there is no argument to pass. Contrast test_monkeypatch.py's
    argument about seams you DO own.
    """
    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        vault.put(uf2, manifest_for(uf2))

    assert len(vault) == 0
    leftovers = [
        name
        for _root, _dirs, files in os.walk(vault.root)
        for name in files
    ]
    assert leftovers == [], "a .part file survived a failed write: " + str(leftovers)


def test_the_temp_file_is_on_the_same_filesystem(vault, uf2):
    """os.replace is atomic only within one filesystem. A temp file in the
    system temp dir and a `shutil.move` across devices is a COPY, and a copy is
    exactly the torn write this design avoids.

    Asserted structurally -- the temp lives in the destination directory --
    because there is no portable way to assert atomicity itself.
    """
    seen = []
    real_mkstemp = __import__("tempfile").mkstemp

    def spy(*args, **kwargs):
        seen.append(kwargs.get("dir"))
        return real_mkstemp(*args, **kwargs)

    import tempfile

    original = tempfile.mkstemp
    tempfile.mkstemp = spy
    try:
        digest, _created = vault.put(uf2, manifest_for(uf2))
    finally:
        tempfile.mkstemp = original

    expected = os.path.join(vault.root, digest[:2])
    assert seen == [expected, expected]


# ── path safety ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "hostile",
    [
        "../../etc/passwd",
        "..\\..\\windows\\system32",
        "....//....//etc",
        "/absolute/path",
        "a" * 64 + "/../../escape",
        "",
    ],
    ids=["dotdot", "windows-dotdot", "doubled", "absolute", "suffix", "empty"],
)
def test_a_client_controlled_key_cannot_escape_the_root(vault, hostile):
    """The important part is not the list. It is that this list can never be
    complete -- there is always another encoding -- so the design does not rely
    on it.

    The key is never sanitised, it is REGENERATED: `put` hashes the bytes
    itself and ignores whatever anyone called them. `has()` on a hostile string
    is therefore just a miss, and no amount of creative encoding changes that.
    A sanitising implementation would need this list to be exhaustive, and it
    never is.
    """
    assert vault.has(hostile) is False


def test_the_traversal_test_is_not_vacuous(vault, uf2):
    """The guard on the test above. If `has()` returned False for everything,
    the whole parametrized sweep would pass against a store that does not
    work."""
    digest, _created = vault.put(uf2, manifest_for(uf2))
    assert vault.has(digest) is True


def test_nothing_is_written_outside_the_root(tmp_path, uf2):
    """Belt and braces: after a normal store, the only files that exist under
    the parent directory are inside the vault. Catches an absolute path built
    by accident, which no traversal string test would."""
    root = tmp_path / "vault"
    sibling = tmp_path / "sibling"
    sibling.mkdir()

    store = Store(root)
    store.put(uf2, manifest_for(uf2))

    assert list(sibling.iterdir()) == []
    written = {p for p in tmp_path.rglob("*") if p.is_file()}
    assert all(str(p).startswith(str(root)) for p in written)


# ── manifests ───────────────────────────────────────────────────────────────

def test_the_manifest_is_json_on_disk(vault, uf2):
    digest, _created = vault.put(uf2, manifest_for(uf2))
    manifest = vault.manifest(digest)
    assert manifest["family"] == "RP2040"
    assert manifest["schema_version"] == 3


def test_manifest_json_is_deterministic(tmp_path, uf2):
    """sort_keys=True, so the same artifact produces byte-identical manifests
    in two different vaults. Without it, a diff of two vaults is noise and
    nobody can tell whether they hold the same thing."""
    a = Store(tmp_path / "a")
    b = Store(tmp_path / "b")
    digest, _created = a.put(uf2, manifest_for(uf2))
    b.put(uf2, manifest_for(uf2))

    left = os.path.join(a.root, digest[:2], digest + ".json")
    right = os.path.join(b.root, digest[:2], digest + ".json")
    assert open(left, "rb").read() == open(right, "rb").read()


def test_fan_out_keeps_directories_small(vault):
    """Two-level sharding, asserted rather than assumed. A flat directory with
    100k entries is slow on every filesystem and unusable on some."""
    for n in range(1, 12):
        blob = build_uf2(blocks=n)
        vault.put(blob, manifest_for(blob))

    shards = os.listdir(vault.root)
    assert all(len(name) == 2 for name in shards)
    assert len(vault) == 11
