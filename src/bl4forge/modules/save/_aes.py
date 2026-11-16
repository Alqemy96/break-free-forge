"""AES-256 in ECB mode, pure stdlib. Block primitives for the save container only.

ECB is the game's own (weak) scheme for save files; do not reuse this for anything else. Tables are
built at import time from the field arithmetic and are never mutated afterwards. Checked against the
FIPS-197 AES-256 example vector by `known_answer()` (used by the module's health check).
"""
from __future__ import annotations

from typing import List

from ...core.errors import SaveError


def _build_sbox() -> List[int]:
    sbox = [0] * 256
    p = q = 1
    while True:
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)           # p *= 3
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF                                                       # q /= 3
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1) | (q >> 7)) & 0xFF ^ ((q << 2) | (q >> 6)) & 0xFF \
            ^ ((q << 3) | (q >> 5)) & 0xFF ^ ((q << 4) | (q >> 4)) & 0xFF
        sbox[p] = (x ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox


_SBOX = _build_sbox()
_INV = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV[_v] = _i


def _xt(a: int) -> int:
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def _mul(a: int, b: int) -> int:
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xt(a)
        b >>= 1
    return r


_M9 = [_mul(i, 9) for i in range(256)]
_M11 = [_mul(i, 11) for i in range(256)]
_M13 = [_mul(i, 13) for i in range(256)]
_M14 = [_mul(i, 14) for i in range(256)]
_RC = (1, 2, 4, 8, 16, 32, 64, 128, 27, 54)


def expand_key(key: bytes) -> List[List[int]]:
    if len(key) != 32:
        raise SaveError("AES-256 needs a 32-byte key, got %d bytes" % len(key))
    w = [list(key[i:i + 4]) for i in range(0, 32, 4)]
    for i in range(8, 60):
        t = list(w[i - 1])
        if i % 8 == 0:
            t = [_SBOX[t[1]] ^ _RC[i // 8 - 1], _SBOX[t[2]], _SBOX[t[3]], _SBOX[t[0]]]
        elif i % 8 == 4:
            t = [_SBOX[b] for b in t]
        w.append([a ^ b for a, b in zip(w[i - 8], t)])
    return [sum((w[4 * r + c] for c in range(4)), []) for r in range(15)]


def _decrypt_block(rk: List[List[int]], blk: bytes) -> bytes:
    s = [a ^ b for a, b in zip(blk, rk[14])]
    for r in range(13, -1, -1):
        t = [0] * 16
        for c in range(4):
            for rr in range(4):
                t[4 * ((c + rr) % 4) + rr] = _INV[s[4 * c + rr]]
        s = [a ^ b for a, b in zip(t, rk[r])]
        if r:
            n = [0] * 16
            for c in range(4):
                a0, a1, a2, a3 = s[4 * c:4 * c + 4]
                n[4 * c] = _M14[a0] ^ _M11[a1] ^ _M13[a2] ^ _M9[a3]
                n[4 * c + 1] = _M9[a0] ^ _M14[a1] ^ _M11[a2] ^ _M13[a3]
                n[4 * c + 2] = _M13[a0] ^ _M9[a1] ^ _M14[a2] ^ _M11[a3]
                n[4 * c + 3] = _M11[a0] ^ _M13[a1] ^ _M9[a2] ^ _M14[a3]
            s = n
    return bytes(s)


def _encrypt_block(rk: List[List[int]], blk: bytes) -> bytes:
    s = [a ^ b for a, b in zip(blk, rk[0])]
    for r in range(1, 15):
        s = [_SBOX[b] for b in s]
        t = [0] * 16
        for c in range(4):
            for rr in range(4):
                t[4 * c + rr] = s[4 * ((c + rr) % 4) + rr]
        s = t
        if r < 14:
            n = [0] * 16
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                for i in range(4):
                    n[4 * c + i] = _xt(a[i]) ^ _xt(a[(i + 1) % 4]) ^ a[(i + 1) % 4] ^ a[(i + 2) % 4] ^ a[(i + 3) % 4]
            s = n
        s = [a ^ b for a, b in zip(s, rk[r])]
    return bytes(s)


def ecb_decrypt(key: bytes, data: bytes) -> bytes:
    if len(data) % 16:
        raise SaveError("encrypted data is %d bytes, not a multiple of 16" % len(data))
    rk = expand_key(key)
    return b"".join(_decrypt_block(rk, data[i:i + 16]) for i in range(0, len(data), 16))


def ecb_encrypt(key: bytes, data: bytes) -> bytes:
    if len(data) % 16:
        raise SaveError("data to encrypt is %d bytes, not a multiple of 16" % len(data))
    rk = expand_key(key)
    return b"".join(_encrypt_block(rk, data[i:i + 16]) for i in range(0, len(data), 16))


def known_answer() -> bool:
    """FIPS-197 appendix C.3 (AES-256): key 00..1f, block 00112233..ff -> 8ea2b7ca...6089."""
    key = bytes(range(32))
    pt = bytes.fromhex("00112233445566778899aabbccddeeff")
    ct = bytes.fromhex("8ea2b7ca516745bfeafc49904b496089")
    return ecb_encrypt(key, pt) == ct and ecb_decrypt(key, ct) == pt
