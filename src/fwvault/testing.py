"""Test doubles and specimen builders, shipped inside the package.

Not a mistake, and not test code that leaked. A library whose only seam is a
transport protocol owes its users a working fake for that protocol, the same
way httpx ships MockTransport and Django ships a test client. If the fake
lives in tests/ then every downstream user writes their own, and every one of
them gets a detail wrong.

Two families here:

  builders   turn keyword arguments into bytes. `build_uf2(blocks=3,
             bad_end_magic=1)` is a specimen with a defect at a named place,
             which is what a corpus is for.
  doubles    fill the transport seam. Each one records what it was asked.

Everything is deterministic. There is no randomness, no clock, and no network
in this module, so a specimen is identical on every machine and a failure is
reproducible from the arguments in the traceback.
"""

import json
import struct

from .parse import (
    UF2_BLOCK_SIZE,
    UF2_FLAG_FAMILY_ID,
    UF2_MAGIC0,
    UF2_MAGIC1,
    UF2_MAGIC_END,
    UF2_PAYLOAD_MAX,
)
from .signing import Response, TransportError

RP2040 = 0xE48BFF56
NRF52840 = 0xADA52840
UNKNOWN_FAMILY = 0x0BADF00D


def build_uf2(blocks=2, family=RP2040, payload_size=256, base_addr=0x10000000,
              flags=None, bad_start_magic=None, bad_end_magic=None,
              wrong_num_blocks=None, oversized_payload=None, shuffle_block_no=False,
              trailing_garbage=0, addr_step=None):
    """A UF2 image, optionally defective at one named place.

    Every defect argument names a block index (or None), so a test reads as
    "block 1's end magic is wrong" rather than as a byte offset the reader has
    to divide by 512 in their head.
    """
    if flags is None:
        flags = UF2_FLAG_FAMILY_ID if family is not None else 0
    if addr_step is None:
        addr_step = UF2_PAYLOAD_MAX

    out = bytearray()
    for i in range(blocks):
        m0 = 0xDEADBEEF if bad_start_magic == i else UF2_MAGIC0
        m1 = UF2_MAGIC1
        end = 0x00000000 if bad_end_magic == i else UF2_MAGIC_END
        size = oversized_payload if oversized_payload and i == 0 else payload_size
        total = wrong_num_blocks if wrong_num_blocks is not None else blocks
        block_no = (blocks - 1 - i) if shuffle_block_no else i

        header = struct.pack(
            "<8I", m0, m1, flags, base_addr + i * addr_step, size,
            block_no, total, family if family is not None else 0,
        )
        data = bytes(((i + j) & 0xFF) for j in range(UF2_PAYLOAD_MAX))
        out += header + data + struct.pack("<I", end)

    assert len(out) == blocks * UF2_BLOCK_SIZE
    return bytes(out) + b"\x00" * trailing_garbage


def build_elf(machine=0x28, bit64=True, little=True, entry=0x8000, e_type=2,
              truncate_to=None):
    """An ELF header. Only the first 32 bytes are ever read by this package, so
    that is all this builds -- a specimen should be the smallest thing that
    exercises the code, not a realistic file."""
    endian = "<" if little else ">"
    ident = (
        b"\x7fELF"
        + bytes([2 if bit64 else 1, 1 if little else 2, 1, 0, 0])
        + b"\x00" * 7
    )
    rest = struct.pack(endian + "HHI", e_type, machine, 1)
    rest += struct.pack(endian + ("Q" if bit64 else "I"), entry)
    blob = ident + rest
    return blob[:truncate_to] if truncate_to is not None else blob


def signed_body(signer="ci-builder", key_id="k-2f81", revoked=False, signed=True):
    return json.dumps(
        {"signed": signed, "signer": signer, "key_id": key_id, "revoked": revoked}
    ).encode("utf-8")


class RecordingTransport:
    """Answers from a dict of url-suffix -> Response, and remembers every call.

    A fake, not a mock: it has real behaviour (routing) and real state you
    interrogate afterwards. Nothing here asserts. Assertions belong in the
    test, where the failure message can say what the test wanted.
    """

    def __init__(self, routes=None, default=None):
        self.routes = routes or {}
        self.default = default or Response(404, b"{}")
        self.calls = []

    def request(self, method, url, body=None, headers=None):
        self.calls.append((method, url, body, headers or {}))
        for suffix, response in self.routes.items():
            if url.endswith(suffix):
                if isinstance(response, Exception):
                    raise response
                return response
        return self.default

    @property
    def urls(self):
        return [url for _m, url, _b, _h in self.calls]


class ScriptedTransport:
    """Answers a fixed sequence, one per call, and raises anything that is an
    exception instance. For testing retry loops, where WHEN a response arrives
    is the behaviour under test.

    Running off the end is a hard failure rather than a repeat of the last
    item. A double that quietly keeps answering turns "retried 3 times" and
    "retried 300 times" into the same passing test.
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def request(self, method, url, body=None, headers=None):
        self.calls.append((method, url, body, headers or {}))
        if not self.script:
            raise AssertionError(
                "ScriptedTransport exhausted: call {} was not scripted "
                "({} {})".format(len(self.calls), method, url)
            )
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def exhausted(self):
        return not self.script


def flaky(times, then, error=None):
    """A script: `times` failures, then `then`. The idiom is common enough that
    spelling it out inline three times is worse than naming it."""
    return [error or TransportError("connection reset")] * times + [then]
