"""The save file container: AES-256-ECB( zlib(yaml) + footer ), PKCS7 padded (the game omits the padding when the length is already a multiple of 16; decrypt accepts both). Pure functions on bytes.

PS5 (proven on the console 2026-11-14): fixed key, footer = uncompressed length as u32 LE (4 bytes),
no adler32. PC (upstream monokrome/bl4 crypto.rs): key = BASE_KEY with its first 8 bytes XORed with
the Steam ID as a u64 LE, footer = adler32 of the YAML (u32 LE) + length (u32 LE).
Decryption is strict: wrong key / corrupt data raises SaveError instead of returning junk.
"""
from __future__ import annotations

import struct
import zlib

from ...core.errors import SaveError
from ._aes import ecb_decrypt, ecb_encrypt

ZLIB_LEVEL = 9      # the game accepts it (header 78 da) although it writes 78 9c itself


def pkcs7_pad(data: bytes) -> bytes:
    n = 16 - len(data) % 16
    return data + bytes([n]) * n


def pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise SaveError("empty data after decryption")
    n = data[-1]
    if not 1 <= n <= 16 or data[-n:] != bytes([n]) * n:
        raise SaveError("bad PKCS7 padding after decryption (wrong key, or not a save of this platform)")
    return data[:-n]


def _inflate(plain: bytes, footer_len: int, what: str):
    d = zlib.decompressobj()
    try:
        yaml = d.decompress(plain)
    except zlib.error as ex:
        raise SaveError("%s: zlib stream is corrupt (%s); wrong key or platform?" % (what, ex)) from None
    if not d.eof:
        raise SaveError("%s: zlib stream is truncated" % what)
    if len(d.unused_data) != footer_len:
        raise SaveError("%s: expected a %d-byte footer after the zlib stream, found %d bytes"
                        % (what, footer_len, len(d.unused_data)))
    return yaml, d.unused_data


def _unwrap(plain: bytes, platform: str) -> bytes:
    if platform == "ps5":
        yaml, footer = _inflate(plain, 4, "ps5 save")
        (length,) = struct.unpack("<I", footer)
        if length != len(yaml):
            raise SaveError("ps5 save: footer length %d != decompressed length %d" % (length, len(yaml)))
    elif platform == "pc":
        yaml, footer = _inflate(plain, 8, "pc save")
        adler, length = struct.unpack("<II", footer)
        if length != len(yaml):
            raise SaveError("pc save: footer length %d != decompressed length %d" % (length, len(yaml)))
        if adler != zlib.adler32(yaml):
            raise SaveError("pc save: footer adler32 does not match the decompressed data")
    else:
        raise SaveError("unknown platform %r" % platform)
    return yaml


def decrypt(data: bytes, key: bytes, platform: str) -> bytes:
    """Encrypted save bytes -> YAML bytes. platform is 'ps5' or 'pc'.

    Real game saves whose zlib+footer length is already a multiple of 16 carry NO PKCS7 padding, so when the
    padded reading fails validation the unpadded plaintext is tried (zlib stream + footer must still verify).
    """
    raw = ecb_decrypt(key, bytes(data))
    try:
        return _unwrap(pkcs7_unpad(raw), platform)
    except SaveError as padded_error:
        try:
            return _unwrap(raw, platform)
        except SaveError:
            raise padded_error from None


def encrypt(yaml: bytes, key: bytes, platform: str) -> bytes:
    """YAML bytes -> encrypted save bytes, padded the way the game's writer pads.

    The game writes NO PKCS7 padding when zlib+footer is already a multiple of 16 (proven on PS5,
    docs/runbooks/RESEARCHER.md), so encrypt does the same; otherwise it PKCS7-pads to the next boundary.
    UNVERIFIED: whether the game's loader would also ACCEPT a padded block-aligned save (the form this
    function produced before) - that needs a real console test nobody has run. Also UNVERIFIED: that the
    PC writer omits padding the same way (only PS5 was observed); PC uses the same rule here.
    """
    packed = zlib.compress(bytes(yaml), ZLIB_LEVEL)
    if platform == "ps5":
        packed += struct.pack("<I", len(yaml) & 0xFFFFFFFF)
    elif platform == "pc":
        packed += struct.pack("<II", zlib.adler32(yaml), len(yaml) & 0xFFFFFFFF)
    else:
        raise SaveError("unknown platform %r" % platform)
    if len(packed) % 16 == 0:
        return ecb_encrypt(key, packed)
    return ecb_encrypt(key, pkcs7_pad(packed))


def pc_key(base_key: bytes, steam_id: str) -> bytes:
    """BASE_KEY with its first 8 bytes XORed with the Steam ID (digits only) as a u64 LE."""
    digits = "".join(c for c in str(steam_id) if c in "0123456789")
    if not digits:
        raise SaveError("Steam ID must contain digits, got %r" % (steam_id,))
    num = int(digits)
    if num >= 1 << 64:
        raise SaveError("Steam ID does not fit in 64 bits")
    key = bytearray(base_key)
    for i, b in enumerate(num.to_bytes(8, "little")):
        key[i] ^= b
    return bytes(key)
