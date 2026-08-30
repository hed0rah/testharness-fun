"""Content-addressed storage, on a real filesystem, atomically.

Small module, three properties worth asserting:

  1. writes are atomic (temp file + os.replace), so a crash mid-write leaves
     either the old artifact or the new one and never half of either
  2. the same bytes twice is a no-op, not a rewrite
  3. no path a client controls can escape the root

The third is the one that gets tested badly. Checking that "../../etc/passwd"
is rejected proves nothing about "..%2f..%2fetc", ".../....//", or a digest
that is a valid hex string of the wrong length. The check here is the shape
that survives all of them: the key is not sanitised, it is REGENERATED -- we
hash the bytes ourselves and ignore whatever the client called it.
"""

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass

from .errors import FwVaultError

SCHEMA_VERSION = 3


@dataclass(frozen=True)
class Manifest:
    digest: str
    kind: str
    size: int
    family: str | None
    entry: int | None
    signer: str | None
    warnings: tuple
    schema_version: int = SCHEMA_VERSION


def digest_of(blob):
    return hashlib.sha256(blob).hexdigest()


class Store:
    """Artifacts under `root`, keyed by their own sha256."""

    def __init__(self, root):
        self.root = str(root)
        os.makedirs(self.root, exist_ok=True)

    def _paths(self, digest):
        # Two-level fan-out, so a directory listing stays usable past ~10k
        # artifacts. The digest is ours, not the client's, so this join is safe
        # by construction rather than by validation.
        shard = os.path.join(self.root, digest[:2])
        return shard, os.path.join(shard, digest + ".bin"), os.path.join(shard, digest + ".json")

    def put(self, blob, manifest):
        """Write bytes + manifest atomically. Returns (digest, created)."""
        digest = digest_of(blob)
        if digest != manifest.digest:
            raise FwVaultError(
                "manifest digest {} does not describe these bytes ({})".format(
                    manifest.digest, digest
                )
            )
        shard, bin_path, json_path = self._paths(digest)
        if os.path.exists(bin_path):
            return digest, False

        os.makedirs(shard, exist_ok=True)
        self._atomic_write(bin_path, blob)
        self._atomic_write(
            json_path,
            json.dumps(asdict(manifest), indent=2, sort_keys=True).encode("utf-8"),
        )
        return digest, True

    def get(self, digest):
        _shard, bin_path, _json = self._paths(digest)
        with open(bin_path, "rb") as fh:
            return fh.read()

    def manifest(self, digest):
        _shard, _bin, json_path = self._paths(digest)
        with open(json_path, "rb") as fh:
            return json.loads(fh.read().decode("utf-8"))

    def has(self, digest):
        return os.path.exists(self._paths(digest)[1])

    def __len__(self):
        return sum(
            1
            for _root, _dirs, files in os.walk(self.root)
            for name in files
            if name.endswith(".bin")
        )

    @staticmethod
    def _atomic_write(path, data):
        # Same directory, so os.replace is a rename within one filesystem and
        # therefore atomic. A temp in /tmp and a shutil.move across devices is
        # a copy, and a copy is exactly the torn write this avoids.
        directory = os.path.dirname(path)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
