"""save_fix + checksums: published test vectors, and a synthetic save that is corrupted, fails verify,
is fixed, and verifies again. Throwaway key only (bytes(range(32)), the FIPS-197 example key), never a
game key."""
from __future__ import annotations

from dataclasses import replace

import pytest

from bl4forge.core.errors import SaveError
from bl4forge.modules import checksums as cs
from bl4forge.tools import save_fix as sf

TEST_KEY = bytes(range(32))
BODY = b"hp: 100\ngold: 250\nname: Tester\n" * 3


# ---------------------------------------------------------------- checksum vectors
def test_crc32_and_adler32_vectors():
    assert cs.crc32(b"123456789") == 0xCBF43926            # the CRC-32 check value
    assert cs.adler32(b"Wikipedia") == 0x11E60398
    assert cs.crc32(b"6789", cs.crc32(b"12345")) == 0xCBF43926   # chaining


def test_fnv1a_vectors():
    assert cs.fnv1a_32(b"") == 0x811C9DC5
    assert cs.fnv1a_32(b"a") == 0xE40C292C
    assert cs.fnv1a_64(b"") == 0xCBF29CE484222325
    assert cs.fnv1a_64(b"a") == 0xAF63DC4C8601EC8C


def test_joaat_vectors_and_seed():
    assert cs.joaat(b"a") == 0xCA2E9442
    assert cs.joaat(b"The quick brown fox jumps over the lazy dog") == 0x519E91F5
    assert cs.joaat(b"a", cs.JOAAT_SEED_GTA5) != cs.joaat(b"a")
    seeded = cs.get("joaat:0x3FAC7125")
    assert seeded.compute(b"a") == cs.joaat(b"a", 0x3FAC7125)


def test_digests_and_lookup():
    assert cs.md5(b"").hex() == "d41d8cd98f00b204e9800998ecf8427e"
    assert cs.sha256(b"abc").hex().startswith("ba7816bf")
    assert cs.get("CRC32").digest(b"123456789", "big") == bytes.fromhex("cbf43926")
    assert cs.get("crc32").digest(b"123456789", "little") == bytes.fromhex("2639f4cb")
    assert cs.get("sha1").digest(b"", "big") == cs.sha1(b"")          # byte order ignored for digests
    with pytest.raises(ValueError):
        cs.get("crc64")


# ---------------------------------------------------------------- the synthetic save
def test_demo_save_corrupt_verify_fix_verify():
    fixer = sf.FIXERS["demo"]
    good = sf.demo_save(BODY)
    assert good[:4] == sf.DEMO_MAGIC
    assert fixer.verify(good).ok
    assert fixer.verify(good).offset == 12

    bad = bytearray(good)
    bad[sf.DEMO_HEADER + 5] ^= 0x01                  # an "edit" that did not update the checksum
    bad = bytes(bad)
    res = fixer.verify(bad)
    assert not res.ok and res.stored == good[12:16]

    fixed = fixer.fix(bad)
    assert fixer.verify(fixed).ok
    assert fixed[:12] == bad[:12] and fixed[16:] == bad[16:]     # only the field changed
    assert fixer.fix(fixed) == fixed                             # idempotent


def test_demo_wrong_magic_refused():
    with pytest.raises(SaveError):
        sf.FIXERS["demo"].verify(b"NOPE" + bytes(40))


def test_tail_locator_with_skip_coverage():
    f = sf.ChecksumFixer("t", "test", "adler32", sf.Locator.tail(4), byteorder="big",
                         coverage=sf.Coverage(field="skip"))
    data = BODY + bytes(4)
    fixed = f.fix(data)
    assert fixed[-4:] == cs.adler32(BODY).to_bytes(4, "big")
    assert f.verify(fixed).ok and not f.verify(data).ok


def test_struct_locator_through_pointer():
    # u32 at offset 4 points to a struct at 32; the fnv1a_64 field is 8 bytes into it; hash covers 16..end.
    f = sf.ChecksumFixer("p", "test", "fnv1a_64", sf.Locator.struct(field=8, base_ptr=4),
                         coverage=sf.Coverage(start=16, field="zero"))
    data = bytearray(64)
    data[4:8] = (32).to_bytes(4, "little")
    data[48:56] = b"payload!"
    fixed = f.fix(bytes(data))
    assert f.verify(fixed).offset == 40
    expect = bytearray(fixed[16:])
    expect[24:32] = bytes(8)
    assert fixed[40:48] == cs.fnv1a_64(bytes(expect)).to_bytes(8, "little")


def test_locator_out_of_range():
    f = sf.ChecksumFixer("x", "test", "crc32", sf.Locator.fixed(100))
    with pytest.raises(SaveError):
        f.verify(bytes(20))


def test_encrypted_layer_roundtrip():
    enc = replace(sf.FIXERS["demo"], name="demo-enc", layer="aes256-ecb-pkcs7")
    bad = bytearray(sf.demo_save(BODY))
    bad[-1] ^= 0xFF
    blob = sf.close_layer(bytes(bad), enc.layer, TEST_KEY)
    assert not enc.verify(sf.open_layer(blob, enc.layer, TEST_KEY)).ok
    fixed_blob = sf.close_layer(enc.fix(sf.open_layer(blob, enc.layer, TEST_KEY)), enc.layer, TEST_KEY)
    assert enc.verify(sf.open_layer(fixed_blob, enc.layer, TEST_KEY)).ok
    with pytest.raises(SaveError):
        sf.open_layer(blob, enc.layer, None)


# ---------------------------------------------------------------- CLI
def _write(path, data):
    path.write_bytes(data)
    return str(path)


def test_cli_plaintext(tmp_path, capsys):
    bad = bytearray(sf.demo_save(BODY))
    bad[20] ^= 0x10
    src = _write(tmp_path / "slot1.sav", bytes(bad))
    assert sf.main(["verify", src, "--game", "demo"]) == 1
    assert sf.main(["fix", src, "--game", "demo"]) == 0
    out = str(tmp_path / "slot1.fixed.sav")
    assert sf.main(["verify", out, "--game", "demo"]) == 0
    assert (tmp_path / "slot1.sav").read_bytes() == bytes(bad)          # input untouched
    assert sf.main(["fix", src, "--game", "demo"]) == 2                # existing output refused
    assert sf.main(["fix", src, "--game", "demo", "--overwrite"]) == 0
    assert sf.main(["fix", src, "--game", "demo", "-o", src]) == 2      # never onto the input
    assert sf.main(["verify", src, "--game", "nosuchgame"]) == 2
    capsys.readouterr()
    assert sf.main(["list"]) == 0
    assert "DEMO DATA" in capsys.readouterr().out


def test_cli_encrypted_with_key_file(tmp_path, capsys):
    enc = replace(sf.FIXERS["demo"], name="demo-enc", layer="aes256-ecb-pkcs7")
    table = {"demo-enc": enc}
    bad = bytearray(sf.demo_save(BODY))
    bad[30] ^= 0x01
    src = _write(tmp_path / "enc.sav", sf.close_layer(bytes(bad), enc.layer, TEST_KEY))
    key_hex = _write(tmp_path / "key.txt", TEST_KEY.hex().encode("ascii") + b"\n")
    key_raw = _write(tmp_path / "key.bin", TEST_KEY)

    assert sf.main(["verify", src, "--game", "demo-enc"], table) == 2                  # no key
    assert sf.main(["verify", src, "--game", "demo-enc", "--key-file", key_hex], table) == 1
    out = str(tmp_path / "enc.out")
    assert sf.main(["fix", src, "--game", "demo-enc", "--key-file", key_hex, "-o", out], table) == 0
    assert sf.main(["verify", out, "--game", "demo-enc", "--key-file", key_raw], table) == 0

    wrong = _write(tmp_path / "wrong.bin", bytes(32))
    assert sf.main(["verify", out, "--game", "demo-enc", "--key-file", wrong], table) == 2
    short = _write(tmp_path / "short.txt", b"00112233")
    assert sf.main(["verify", out, "--game", "demo-enc", "--key-file", short], table) == 2

    printed = capsys.readouterr()
    assert TEST_KEY.hex() not in printed.out + printed.err                   # the key is never echoed
