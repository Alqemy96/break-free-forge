"""save_verify on synthetic saves: a small fake YAML, zlib'd, trailered, padded (or not) and encrypted with a
throwaway key built HERE, independently of `_container.encrypt`, so the oracle is checked against a second
implementation of the format rather than against itself. Stdlib only (unittest; pytest collects it too)."""
from __future__ import annotations

import io
import os
import struct
import tempfile
import unittest
import zlib
from contextlib import redirect_stderr, redirect_stdout

from bl4forge.modules.save import _aes
from bl4forge.tools import save_verify as sv

TEST_KEY = bytes(range(32))            # the FIPS-197 example key: a throwaway, NOT a game key
OTHER_KEY = bytes(range(1, 33))        # a second throwaway, for the wrong-key case

YAML = (
    "state: \n"
    "  char_name: Test\n"
    "  experience: \n"
    "  - type: character\n"
    "    level: 5\n"
    "    points: 100\n"
    "  inventory: \n"
    "    items: \n"
    "      backpack: \n"
    "        slot_0: \n"
    "          serial: '@Ugabc'\n"
    "  currencies: \n"
    "    cash: 10\n"
    "    eridium: 7\n"
)
CASH_LINE = 13                          # 1-based line of "    cash: 10"


def pkcs7(data: bytes) -> bytes:
    n = 16 - len(data) % 16
    return data + bytes([n]) * n


def packed(yaml: str, trailer_len=None) -> bytes:
    raw = yaml.encode("utf-8")
    return zlib.compress(raw, 9) + struct.pack("<I", len(raw) if trailer_len is None else trailer_len)


def make_save(yaml: str, key: bytes = TEST_KEY, pad: bool = True, trailer_len=None) -> bytes:
    body = packed(yaml, trailer_len)
    if pad:
        body = pkcs7(body)
    assert len(body) % 16 == 0, "unpadded saves need a block-aligned payload"
    return _aes.ecb_encrypt(key, body)


def aligned_yaml() -> str:
    """YAML whose zlib stream + 4-byte trailer is a multiple of 16: the case the game writes with NO padding."""
    for n in range(1, 2000):
        filler = "".join(chr(97 + (i * 7 + i // 3) % 26) for i in range(n))
        y = YAML + "  note: %s\n" % filler
        if len(packed(y)) % 16 == 0:
            return y
    raise AssertionError("no block-aligned variant found")


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.key_file = self.put("key.hex", TEST_KEY.hex() + "\n")

    def tearDown(self):
        self._tmp.cleanup()

    def put(self, name: str, content) -> str:
        path = os.path.join(self.dir, name)
        with open(path, "wb") as fh:
            fh.write(content.encode("utf-8") if isinstance(content, str) else content)
        return path

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = sv.main(list(argv))
            except SystemExit as ex:          # argparse usage errors
                code = ex.code
        text = out.getvalue() + err.getvalue()
        self.assertNotIn(TEST_KEY.hex(), text.lower(), "the key must never be printed")
        self.assertNotIn(repr(TEST_KEY), text)
        return code, out.getvalue(), err.getvalue()

    def roundtrip(self, original: str, edited, plan: str, *extra, edited_bytes=None):
        o = self.put("orig.sav", make_save(original))
        e = self.put("edit.sav", edited_bytes if edited_bytes is not None else make_save(edited))
        p = self.put("plan.txt", plan)
        return self.run_cli("roundtrip", o, e, "--key-file", self.key_file, "--expected-diff", p, *extra)


class OracleTests(Base):
    def test_padded_save_passes(self):
        res = sv.oracle(make_save(YAML), TEST_KEY, "ps5")
        self.assertTrue(res.ok)
        self.assertEqual(res.reading, "padded")
        self.assertEqual(res.plaintext, YAML.encode())

    def test_block_aligned_unpadded_save_passes(self):
        y = aligned_yaml()
        res = sv.oracle(make_save(y, pad=False), TEST_KEY, "ps5")
        self.assertTrue(res.ok, res.checks)
        self.assertEqual(res.reading, "unpadded")
        self.assertEqual(res.plaintext, y.encode())

    def test_aligned_but_padded_is_flagged_info_not_fail(self):
        res = sv.oracle(make_save(aligned_yaml(), pad=True), TEST_KEY, "ps5")
        self.assertTrue(res.ok)
        self.assertTrue(any(c.status == sv.INFO and "UNVERIFIED" in c.detail for c in res.checks))

    def test_wrong_key_fails(self):
        res = sv.oracle(make_save(YAML, key=OTHER_KEY), TEST_KEY, "ps5")
        self.assertFalse(res.ok)
        self.assertIsNone(res.plaintext)

    def test_bad_trailer_fails(self):
        res = sv.oracle(make_save(YAML, trailer_len=len(YAML) + 1), TEST_KEY, "ps5")
        self.assertFalse(res.ok)
        self.assertTrue(any(c.status == sv.FAIL and "trailer length" in c.name for c in res.checks))

    def test_truncated_ciphertext_fails(self):
        res = sv.oracle(make_save(YAML)[:-5], TEST_KEY, "ps5")
        self.assertFalse(res.ok)
        self.assertEqual(res.checks[0].status, sv.FAIL)

    def test_pc_trailer_with_adler_passes(self):
        raw = YAML.encode()
        body = pkcs7(zlib.compress(raw, 9) + struct.pack("<II", zlib.adler32(raw), len(raw)))
        steam = "76561198000000000"
        pc_key = sv._container.pc_key(TEST_KEY, steam)          # base key + Steam ID, via the existing helper
        save = self.put("pc.sav", _aes.ecb_encrypt(pc_key, body))
        code, out, _ = self.run_cli("oracle", save, "--key-file", self.key_file, "--platform", "pc",
                                    "--steam-id", steam)
        self.assertEqual(code, 0, out)
        self.assertIn("PASS  padded: trailer adler32 matches", out)
        code, _, err = self.run_cli("oracle", save, "--key-file", self.key_file, "--platform", "pc")
        self.assertEqual(code, 2)
        self.assertIn("--steam-id", err)

    def test_cli_exit_codes_and_report(self):
        good = self.put("good.sav", make_save(YAML))
        bad = self.put("bad.sav", make_save(YAML, key=OTHER_KEY))
        code, out, _ = self.run_cli("oracle", good, "--key-file", self.key_file)
        self.assertEqual(code, 0)
        self.assertIn("ORACLE PASS", out)
        self.assertIn("PASS  padded: zlib stream is complete", out)
        code, out, _ = self.run_cli("oracle", bad, "--key-file", self.key_file)
        self.assertEqual(code, 1)
        self.assertIn("ORACLE FAIL", out)


class KeyFileTests(Base):
    def test_raw_32_bytes_accepted(self):
        raw = self.put("key.bin", TEST_KEY)
        code, _, _ = self.run_cli("oracle", self.put("s.sav", make_save(YAML)), "--key-file", raw)
        self.assertEqual(code, 0)

    def test_bad_key_file_is_usage_error_without_echo(self):
        secretish = "zz" + TEST_KEY.hex()[2:]          # almost a key; must not be echoed
        kf = self.put("bad.key", secretish)
        code, out, err = self.run_cli("oracle", self.put("s.sav", make_save(YAML)), "--key-file", kf)
        self.assertEqual(code, 2)
        self.assertIn("neither 64 hex digits nor 32 raw bytes", err)
        self.assertNotIn(secretish, out + err)

    def test_missing_key_file(self):
        code, _, err = self.run_cli("oracle", self.put("s.sav", make_save(YAML)), "--key-file",
                                    os.path.join(self.dir, "nope.key"))
        self.assertEqual(code, 2)
        self.assertIn("cannot read key file", err)


class PlanTests(unittest.TestCase):
    def test_grammar(self):
        plan = sv.parse_plan("# c\n\n13\n13 =     cash: 5\n=     cash: 5\nkey state/currencies/cash\n"
                             "key state/currencies/cash = 5\n")
        self.assertEqual([(e.line, e.path, e.content) for e in plan], [
            (13, None, None), (13, None, "    cash: 5"), (None, None, "    cash: 5"),
            (None, "state/currencies/cash", None), (None, "state/currencies/cash", "5")])

    def test_bad_line_rejected(self):
        with self.assertRaises(sv.SaveError):
            sv.parse_plan("thirteen\n")


class RoundtripTests(Base):
    def test_planned_line_number_passes(self):
        code, out, _ = self.roundtrip(YAML, YAML.replace("cash: 10", "cash: 5"), "%d\n" % CASH_LINE)
        self.assertEqual(code, 0, out)
        self.assertIn("ROUNDTRIP PASS", out)
        self.assertIn("every unlisted line is byte-identical", out)
        self.assertIn("PASS  re-encrypted EDITED plaintext passes the oracle", out)

    def test_planned_by_content_and_key_passes(self):
        edited = YAML.replace("cash: 10", "cash: 5").replace("level: 5", "level: 6")
        code, out, _ = self.roundtrip(YAML, edited, "=     cash: 5\nkey state/experience/-/level = 6\n")
        self.assertEqual(code, 0, out)

    def test_unplanned_change_fails_and_is_named(self):
        edited = YAML.replace("cash: 10", "cash: 5").replace("eridium: 7", "eridium: 999")
        code, out, _ = self.roundtrip(YAML, edited, "%d\n" % CASH_LINE)
        self.assertEqual(code, 1)
        self.assertIn("UNEXPECTED  line 14  (state/currencies/eridium)", out)
        self.assertIn("'    eridium: 999'", out)
        self.assertIn("ROUNDTRIP FAIL", out)

    def test_planned_edit_missing_fails(self):
        code, out, _ = self.roundtrip(YAML, YAML, "%d = cash: 5\n" % CASH_LINE)
        self.assertEqual(code, 1)
        self.assertIn("PLANNED BUT NOT FOUND", out)

    def test_wrong_new_value_fails(self):
        code, out, _ = self.roundtrip(YAML, YAML.replace("cash: 10", "cash: 6"), "%d = cash: 5\n" % CASH_LINE)
        self.assertEqual(code, 1)
        self.assertIn("UNEXPECTED  line 13", out)

    def test_empty_plan_identical_saves_pass(self):
        code, out, _ = self.roundtrip(YAML, YAML, "")
        self.assertEqual(code, 0, out)

    def test_line_ending_change_is_a_difference(self):
        edited = YAML.replace("  char_name: Test\n", "  char_name: Test\r\n")
        code, out, _ = self.roundtrip(YAML, edited, "")
        self.assertEqual(code, 1)
        self.assertIn("line endings differ", out)

    def test_inserted_line_is_unexpected(self):
        edited = YAML + "    golden_keys: 3\n"
        code, out, _ = self.roundtrip(YAML, edited, "")
        self.assertEqual(code, 1)
        self.assertIn("UNEXPECTED", out)

    def test_edited_file_failing_oracle_stops(self):
        code, out, _ = self.roundtrip(YAML, None, "", edited_bytes=make_save(YAML, key=OTHER_KEY))
        self.assertEqual(code, 1)
        self.assertIn("nothing was compared", out)


class ReserializeTests(Base):
    # what a re-serialiser might do: drop `key: ` trailing spaces and switch quote style
    def reserialized(self, text: str) -> str:
        return text.replace(": \n", ":\n").replace("'@Ugabc'", '"@Ugabc"')

    def test_formatting_only_fails_in_byte_mode(self):
        code, out, _ = self.roundtrip(YAML, self.reserialized(YAML), "")
        self.assertEqual(code, 1)

    def test_formatting_only_passes_with_flag_and_says_so(self):
        edited = self.reserialized(YAML.replace("cash: 10", "cash: 5"))
        code, out, _ = self.roundtrip(YAML, edited, "key state/currencies/cash = 5\n", "--allow-reserialize")
        self.assertEqual(code, 0, out)
        self.assertIn("PARSED VALUES (--allow-reserialize)", out)

    def test_unplanned_value_change_still_fails_with_flag(self):
        edited = self.reserialized(YAML.replace("cash: 10", "cash: 5").replace("@Ugabc", "@Ugxyz"))
        code, out, _ = self.roundtrip(YAML, edited, "key state/currencies/cash\n", "--allow-reserialize")
        self.assertEqual(code, 1)
        self.assertIn("state/inventory/items/backpack/slot_0/serial", out)


if __name__ == "__main__":
    unittest.main()
