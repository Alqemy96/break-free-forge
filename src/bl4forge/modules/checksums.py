"""Checksum primitives for save files, pure stdlib. Plain functions on bytes, no state.

Not a cell: this file is a shared library, and it is deliberately NOT in `MODULE_NAMES`, so the
registry never tries to build it. Borderlands 4 itself needs none of it (its YAML has no integrity
field; the zlib stream and the length/adler32 footer are handled by `save/_container.py`). It exists
for games whose decrypted save carries a checksum that must be recomputed after an edit; the per-game
definitions live in `bl4forge.tools.save_fix`.

Integer checksums (crc32, adler32, joaat, fnv1a_*) return an int; the caller picks the byte order when
storing it. Cryptographic digests (md5, sha*) return bytes, which are stored as-is (byte order does
not apply to them).

DISCLOSURE (what this code does)
  Reads: nothing. Writes: nothing. Network: none. Risk: none. Pure arithmetic on bytes it is given.
"""
from __future__ import annotations

import binascii
import hashlib
import zlib
from dataclasses import dataclass
from typing import Callable, Dict, Union

_M32 = 0xFFFFFFFF
_M64 = 0xFFFFFFFFFFFFFFFF

# Recorded from public reverse-engineering write-ups of GTA V saves; UNVERIFIED by this project (we have
# not checked it against a real GTA V save). Kept only as a worked example of a seeded joaat.
JOAAT_SEED_GTA5 = 0x3FAC7125

FNV32_OFFSET = 0x811C9DC5
FNV32_PRIME = 0x01000193
FNV64_OFFSET = 0xCBF29CE484222325
FNV64_PRIME = 0x00000100000001B3


def crc32(data: bytes, init: int = 0) -> int:
    """CRC-32 (IEEE 802.3, the zlib/PNG one). `init` chains a running value across chunks."""
    return binascii.crc32(data, init) & _M32


def adler32(data: bytes, init: int = 1) -> int:
    """Adler-32 as zlib computes it. `init` chains a running value across chunks."""
    return zlib.adler32(data, init) & _M32


def joaat(data: bytes, seed: int = 0) -> int:
    """Bob Jenkins' one-at-a-time hash, 32-bit, with a configurable starting value.

    seed=0 is the textbook hash. Some games start from a fixed non-zero seed; GTA V is the commonly cited
    example with JOAAT_SEED_GTA5 (0x3FAC7125), recorded from public reverse-engineering and UNVERIFIED by us.
    """
    h = seed & _M32
    for b in data:
        h = (h + b) & _M32
        h = (h + (h << 10)) & _M32
        h ^= h >> 6
    h = (h + (h << 3)) & _M32
    h ^= h >> 11
    h = (h + (h << 15)) & _M32
    return h


def fnv1a_32(data: bytes, seed: int = FNV32_OFFSET) -> int:
    """FNV-1a, 32-bit. `seed` defaults to the standard offset basis."""
    h = seed & _M32
    for b in data:
        h = ((h ^ b) * FNV32_PRIME) & _M32
    return h


def fnv1a_64(data: bytes, seed: int = FNV64_OFFSET) -> int:
    """FNV-1a, 64-bit. `seed` defaults to the standard offset basis."""
    h = seed & _M64
    for b in data:
        h = ((h ^ b) * FNV64_PRIME) & _M64
    return h


def md5(data: bytes) -> bytes:
    """MD5 digest (16 bytes). For integrity fields only; it is not a security primitive."""
    return hashlib.md5(data).digest()


def sha1(data: bytes) -> bytes:
    """SHA-1 digest (20 bytes)."""
    return hashlib.sha1(data).digest()


def sha256(data: bytes) -> bytes:
    """SHA-256 digest (32 bytes)."""
    return hashlib.sha256(data).digest()


@dataclass(frozen=True)
class Algorithm:
    """A named checksum: how many bytes its stored value takes and how to compute it."""

    name: str
    size: int
    compute: Callable[[bytes], Union[int, bytes]]

    def digest(self, data: bytes, byteorder: str = "little") -> bytes:
        """The value as it would be stored in the file: ints in `byteorder`, digests as-is."""
        value = self.compute(data)
        if isinstance(value, bytes):
            return value
        return value.to_bytes(self.size, byteorder)


ALGORITHMS: Dict[str, Algorithm] = {
    "crc32": Algorithm("crc32", 4, crc32),
    "adler32": Algorithm("adler32", 4, adler32),
    "joaat": Algorithm("joaat", 4, joaat),
    "fnv1a_32": Algorithm("fnv1a_32", 4, fnv1a_32),
    "fnv1a_64": Algorithm("fnv1a_64", 8, fnv1a_64),
    "md5": Algorithm("md5", 16, md5),
    "sha1": Algorithm("sha1", 20, sha1),
    "sha256": Algorithm("sha256", 32, sha256),
}


def joaat_seeded(seed: int) -> Algorithm:
    """A joaat Algorithm with a fixed seed, e.g. joaat_seeded(JOAAT_SEED_GTA5)."""
    seed &= _M32
    return Algorithm("joaat:0x%08x" % seed, 4, lambda data: joaat(data, seed))


def get(name: str) -> Algorithm:
    """Look up an algorithm by name. 'joaat:<seed>' (decimal or 0x-hex) gives a seeded joaat."""
    key = name.strip().lower()
    if key.startswith("joaat:"):
        try:
            return joaat_seeded(int(key[6:], 0))
        except ValueError:
            raise ValueError("bad joaat seed in %r" % name) from None
    try:
        return ALGORITHMS[key]
    except KeyError:
        raise ValueError("unknown checksum %r; known: %s, joaat:<seed>"
                         % (name, ", ".join(sorted(ALGORITHMS)))) from None
