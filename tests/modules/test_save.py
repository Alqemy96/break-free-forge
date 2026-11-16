"""Tests for the `save` cell: container crypto (PS5 + PC), the line-level YAML editor, copy-only writes.

Real-save tests read the decrypted PS5 saves from the directory named by BL4FORGE_SAVE_FIXTURES
(they hold character data, so they are not committed) and skip when it is unset. They use the PS5 key
from config.toml and FAIL with a clear message when it is missing. Everything else uses a throwaway
key and a small synthetic YAML and always runs.
"""
from __future__ import annotations

import os
import zlib
from dataclasses import replace
from pathlib import Path

import pytest

from bl4forge.core.config import Config
from bl4forge.core.errors import ConfigError, SaveError, SaveKeyMissing
from bl4forge.core.forge import Forge
from bl4forge.core.module import ModuleContext, conformance_problems
from bl4forge.core.ports import SavePort
from bl4forge.modules.save import MODULE as SaveModule, _aes, _container, _yamltext

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ENV = "BL4FORGE_SAVE_FIXTURES"
TEST_KEY = bytes(range(32))
TEST_PC_BASE = bytes(range(100, 132))
STEAM_ID = "76561198000000000"

SYNTH = (
    "state: \n"
    "  resource_pools: \n"
    "  char_name: Hunter\n"
    "  class: Char_ExoSoldier\n"
    "  experience: \n"
    "  - type: character\n"
    "    level: 22\n"
    "    points: 355313\n"
    "  - type: Specialization\n"
    "    level: 1\n"
    "    points: 0\n"
    "  inventory: \n"
    "    items: \n"
    "      backpack: \n"
    "        slot_0: \n"
    "          serial: '@UgAAA'\n"
    "          state_flags: 1\n"
    "        slot_1: \n"
    "          serial: '@UgBBB'\n"
    "          flags: 1\n"
    "    equipped_inventory: \n"
    "      equipped: \n"
    "        slot_3: \n"
    "        - serial: '@UgCCC'\n"
    "          flags: 1\n"
    "        slot_0: \n"
    "        - serial: '@UgDDD'\n"
    "  currencies: \n"
    "    cash: 1000163543\n"
    "    eridium: 1000001124\n"
    "  lostloot: \n"
    "    items: \n"
    "    - serial: '@UgEEE'\n"
    "      in_machine: true\n"
    "    - serial: '@UgFFF'\n"
    "      in_machine: true\n"
    "    slots: 6\n"
    "stats: \n"
    "  serial: 'not-an-item'\n"
)


def make(config=None, **kw):
    config = config or Config.default(root=ROOT)
    return SaveModule(ModuleContext("save", replace(config, **kw), {}))


@pytest.fixture()
def save():
    return make(save_ps5_key=TEST_KEY, save_pc_base_key=TEST_PC_BASE)


# ---- cell wall ---------------------------------------------------------------------------------

def test_cell_declares_itself_and_conforms(save):
    assert (SaveModule.name, SaveModule.requires, SaveModule.port) == ("save", (), SavePort)
    assert conformance_problems(save, SavePort) == []


def test_health_is_honest_and_never_raises(save):
    rep = save.health()
    assert rep.ok, rep
    assert "ps5 key configured" in rep.summary
    assert "NOT configured" in make().health().summary          # key status is reported, not hidden


def test_aes_matches_the_fips_197_vector():
    assert _aes.known_answer()


# ---- keys live in config -----------------------------------------------------------------------

def test_missing_keys_fail_clearly():
    s = make()                                                    # Config.default: no keys
    with pytest.raises(SaveKeyMissing, match=r"\[save\] ps5_key"):
        s.decrypt_ps5(b"\x00" * 16)
    with pytest.raises(SaveKeyMissing, match="pc_base_key"):
        s.encrypt_pc("a: 1\n", STEAM_ID)


def test_config_reads_keys_from_the_save_table(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[save]\nps5_key = "%s"\npc_base_key = "%s"\n' % (TEST_KEY.hex(), TEST_PC_BASE.hex()))
    cfg = Config.load(path=p, root=ROOT)
    assert cfg.save_ps5_key == TEST_KEY and cfg.save_pc_base_key == TEST_PC_BASE
    assert TEST_KEY.hex() not in repr(cfg)                        # never printed by accident


@pytest.mark.parametrize("bad", ['"zz"', '"abcd"', "12"])
def test_config_rejects_bad_keys(tmp_path, bad):
    p = tmp_path / "c.toml"
    p.write_text("[save]\nps5_key = %s\n" % bad)
    with pytest.raises(ConfigError, match="save.ps5_key"):
        Config.load(path=p, root=ROOT)


def test_blank_keys_in_the_example_config_mean_unset(tmp_path):
    cfg = Config.load(path=ROOT / "config.example.toml", root=ROOT)
    assert cfg.save_ps5_key is None and cfg.save_pc_base_key is None


# ---- container ---------------------------------------------------------------------------------

def test_ps5_round_trip_and_layout(save):
    blob = save.encrypt_ps5(SYNTH)
    assert len(blob) % 16 == 0 and save.decrypt_ps5(blob) == SYNTH
    plain = _container.pkcs7_unpad(_aes.ecb_decrypt(TEST_KEY, blob))
    assert plain[:2] == b"\x78\xda"                                # zlib level 9, as the console accepts
    assert plain[-4:] == len(SYNTH.encode()).to_bytes(4, "little")  # LE length trailer, no adler32
    assert zlib.decompress(plain[:-4]) == SYNTH.encode()


def test_pc_round_trip_layout_and_key_derivation(save):
    blob = save.encrypt_pc(SYNTH, STEAM_ID)
    assert save.decrypt_pc(blob, STEAM_ID) == SYNTH
    key = _container.pc_key(TEST_PC_BASE, STEAM_ID)
    sid = int(STEAM_ID).to_bytes(8, "little")
    assert key[:8] == bytes(a ^ b for a, b in zip(TEST_PC_BASE[:8], sid)) and key[8:] == TEST_PC_BASE[8:]
    plain = _container.pkcs7_unpad(_aes.ecb_decrypt(key, blob))
    y = SYNTH.encode()
    assert plain[-8:] == zlib.adler32(y).to_bytes(4, "little") + len(y).to_bytes(4, "little")
    assert save.decrypt_pc(blob, "ID: " + STEAM_ID) == SYNTH      # non-digits are ignored, as upstream


def test_wrong_key_wrong_id_and_wrong_platform_are_refused(save):
    blob = save.encrypt_ps5(SYNTH)
    other = make(save_ps5_key=bytes(reversed(TEST_KEY)))
    with pytest.raises(SaveError):
        other.decrypt_ps5(blob)
    pc = save.encrypt_pc(SYNTH, STEAM_ID)
    with pytest.raises(SaveError):
        save.decrypt_pc(pc, "76561198000000001")
    with pytest.raises(SaveError):                                  # ps5 footer is 4 bytes, pc is 8
        _container.decrypt(_aes.ecb_encrypt(TEST_KEY, _container.pkcs7_pad(
            zlib.compress(b"x") + b"\0" * 8)), TEST_KEY, "ps5")
    with pytest.raises(SaveError, match="multiple of 16"):
        save.decrypt_ps5(b"\x01" * 17)
    with pytest.raises(SaveError, match="Steam ID"):
        save.encrypt_pc(SYNTH, "abc")


def _aligned_yaml():
    """A YAML whose zlib(level 9)+4-byte trailer is already a multiple of 16 (the game then writes no padding)."""
    for n in range(1, 400):
        y = SYNTH + "# " + zlib.crc32(b"%d" % n).to_bytes(4, "big").hex() * n + "\n"
        if (len(zlib.compress(y.encode(), 9)) + 4) % 16 == 0:
            return y
    raise AssertionError("no aligned case found")


def test_ps5_block_aligned_save_without_pkcs7_padding_is_accepted(save):
    y = _aligned_yaml()
    packed = zlib.compress(y.encode(), 9) + len(y.encode()).to_bytes(4, "little")
    assert len(packed) % 16 == 0
    blob = _aes.ecb_encrypt(TEST_KEY, packed)                       # no padding, as the game writes it
    assert len(blob) == len(packed) and save.decrypt_ps5(blob) == y
    assert save.decrypt_ps5(save.encrypt_ps5(y)) == y                # our own (padded) output still loads
    with pytest.raises(SaveError):                                   # unpadded but corrupt trailer still refused
        save.decrypt_ps5(_aes.ecb_encrypt(TEST_KEY, packed[:-4] + (len(y) + 1).to_bytes(4, "little")))


def test_corrupt_footer_is_detected(save):
    y = SYNTH.encode()
    bad = _aes.ecb_encrypt(TEST_KEY, _container.pkcs7_pad(zlib.compress(y) + (len(y) + 1).to_bytes(4, "little")))
    with pytest.raises(SaveError, match="footer length"):
        save.decrypt_ps5(bad)


# ---- text editor -------------------------------------------------------------------------------

def test_list_items_covers_all_three_areas_and_skips_other_serial_keys(save):
    items = save.list_items(SYNTH)
    assert [(i.ref, i.serial) for i in items] == [
        ("backpack/slot_0", "@UgAAA"), ("backpack/slot_1", "@UgBBB"),
        ("equipped/slot_3", "@UgCCC"), ("equipped/slot_0", "@UgDDD"),
        ("lostloot/0", "@UgEEE"), ("lostloot/1", "@UgFFF")]
    lines = SYNTH.split("\n")
    for it in items:                                               # line numbers point at the serial line
        assert it.serial in lines[it.line - 1]


def test_summary(save):
    s = save.summary(SYNTH)
    assert (s["name"], s["class"], s["level"], s["points"], s["items"]) == ("Hunter", "Char_ExoSoldier", 22, 355313, 6)
    assert s["currencies"] == {"cash": 1000163543, "eridium": 1000001124}


def test_currency_patch_changes_exactly_one_line(save):
    new = save.set_currency(SYNTH, "eridium", 222)
    assert save.changed_lines(SYNTH, new) == [(30, "    eridium: 1000001124", "    eridium: 222")]
    assert save.summary(new)["currencies"] == {"cash": 1000163543, "eridium": 222}
    back = save.set_currency(new, "eridium", 1000001124)
    assert back == SYNTH                                           # reversible, byte for byte


def test_patches_keep_line_endings_and_trailing_spaces(save):
    crlf = SYNTH.replace("\n", "\r\n")
    new = save.set_currency(crlf, "cash", 5)
    assert new.replace("\r\n", "\n") == save.set_currency(SYNTH, "cash", 5)
    assert new.count("\r\n") == crlf.count("\r\n")
    assert "state: \r\n" in new                                    # trailing space after the key survived


@pytest.mark.parametrize("name,value,needle", [
    ("gold", 1, "no currency"), ("cash", -1, "from 0"), ("cash", "5", "integer"),
    ("cash", True, "integer"), ("cash", 2 ** 63, "from 0")])
def test_currency_refusals(save, name, value, needle):
    with pytest.raises(SaveError, match=needle):
        save.set_currency(SYNTH, name, value)


def test_progress_patch_touches_only_the_character_entry(save):
    new = save.set_progress(SYNTH, level=30)
    assert save.changed_lines(SYNTH, new) == [(7, "    level: 22", "    level: 30")]
    both = save.set_progress(SYNTH, level=30, points=999)
    assert [n for n, _, _ in save.changed_lines(SYNTH, both)] == [7, 8]
    assert save.summary(both)["level"] == 30 and save.summary(both)["points"] == 999
    for args in ({}, {"level": 0}, {"level": 101}, {"points": -5}):
        with pytest.raises(SaveError):
            save.set_progress(SYNTH, **args)


def test_serial_patch_changes_exactly_one_line_in_every_area(save):
    for it in save.list_items(SYNTH):
        new = save.set_serial(SYNTH, it.ref, "@UgZZZ")
        assert save.changed_lines(SYNTH, new) == [
            (it.line, SYNTH.split("\n")[it.line - 1], SYNTH.split("\n")[it.line - 1].replace(it.serial, "@UgZZZ"))]
        assert {i.ref: i.serial for i in save.list_items(new)}[it.ref] == "@UgZZZ"


def test_serial_refusals_and_quote_escaping(save):
    with pytest.raises(SaveError, match="no item 'backpack/slot_9'"):
        save.set_serial(SYNTH, "backpack/slot_9", "@UgZZZ")
    for bad in ("", "UgZZZ", "@Ug ZZ", "@Ug\nZZ", None):
        with pytest.raises(SaveError, match="not a serial"):
            save.set_serial(SYNTH, "backpack/slot_0", bad)
    new = save.set_serial(SYNTH, "backpack/slot_0", "@Ug'Q")
    assert "serial: '@Ug''Q'" in new and save.list_items(new)[0].serial == "@Ug'Q"


def test_a_save_without_inventory_lists_nothing(save):
    assert save.list_items("state: \n  currencies: \n    cash: 1\n") == []
    with pytest.raises(SaveError, match="no experience"):
        save.set_progress("state: \n  x: 1\n", level=3)


# ---- copy-only writes --------------------------------------------------------------------------

def test_write_copy_never_touches_the_source_and_records_hashes(save, tmp_path):
    src = tmp_path / "gbxsavegame.sav"
    src.write_bytes(save.encrypt_ps5(SYNTH))
    before = src.read_bytes()
    dst = tmp_path / "copy.sav"
    data = save.encrypt_ps5(save.set_currency(SYNTH, "cash", 7))
    rec = save.write_copy(str(src), str(dst), data)
    assert src.read_bytes() == before and dst.read_bytes() == data
    assert rec["source_sha256"] == save.sha256(before) and rec["dest_sha256"] == save.sha256(data)
    assert (tmp_path / "copy.sav.bl4forge.json").is_file()
    with pytest.raises(SaveError, match="already exists"):
        save.write_copy(str(src), str(dst), data)
    save.write_copy(str(src), str(dst), data, overwrite=True)
    with pytest.raises(SaveError, match="refusing to write over the source"):
        save.write_copy(str(src), str(src), data, overwrite=True)
    with pytest.raises(SaveError, match="refusing to write over the source"):
        save.write_copy(str(src), str(tmp_path / "." / "gbxsavegame.sav"), data, overwrite=True)
    assert src.read_bytes() == before


# ---- real saves --------------------------------------------------------------------------------

def _fixtures():
    root = os.environ.get(FIXTURE_ENV)
    return sorted(Path(root).rglob("gbxsavegame.sav")) if root else []


@pytest.fixture(scope="module")
def real():
    if not os.environ.get(FIXTURE_ENV):
        pytest.skip("%s not set (point it at a folder of your own save copies)" % FIXTURE_ENV)
    files = _fixtures()
    assert len(files) == 4, "expected 4 gbxsavegame.sav under %s, found %d" % (os.environ[FIXTURE_ENV], len(files))
    cfg = Config.load()
    if cfg.save_ps5_key is None:
        pytest.fail("PS5 save key missing: set [save] ps5_key in config.toml (or BL4FORGE_CONFIG); "
                    "the real-save tests cannot run without it")
    return make(cfg), files


def test_real_saves_decrypt_encrypt_decrypt_to_identical_yaml(real):
    s, files = real
    for f in files:
        raw = f.read_bytes()
        y1 = s.decrypt_ps5(raw)
        again = s.encrypt_ps5(y1)
        assert s.decrypt_ps5(again) == y1, f
        assert f.read_bytes() == raw                                # the fixture itself is untouched


def test_real_character_save_edits_change_one_line(real):
    s, files = real
    char = [f for f in files if f.parent.name == "sdimg_1"][0]
    y = s.decrypt_ps5(char.read_bytes())
    summ = s.summary(y)
    assert (summ["name"], summ["level"], summ["items"]) == ("Hunter", 22, 54)
    by_area = {a: sum(1 for i in s.list_items(y) if i.area == a) for a in ("backpack", "equipped", "lostloot")}
    assert by_area == {"backpack": 39, "equipped": 9, "lostloot": 6}
    edited = s.set_currency(y, "eridium", 222)
    changes = s.changed_lines(y, edited)
    assert len(changes) == 1 and changes[0][1].strip().startswith("eridium:") and changes[0][2].strip() == "eridium: 222"
    assert s.decrypt_ps5(s.encrypt_ps5(edited)) == edited
    assert s.set_currency(edited, "eridium", summ["currencies"]["eridium"]) == y


def test_real_profile_saves_have_no_items_and_no_crash(real):
    s, files = real
    for f in files:
        if "profile" in f.parent.name:
            assert s.list_items(s.decrypt_ps5(f.read_bytes())) == []


def test_real_save_is_also_a_valid_pc_save_with_an_id(real):
    s, files = real
    y = s.decrypt_ps5(files[0].read_bytes())
    pc = make(save_pc_base_key=Config.load().save_pc_base_key or TEST_PC_BASE)
    assert pc.decrypt_pc(pc.encrypt_pc(y, STEAM_ID), STEAM_ID) == y


# ---- shared point pools (profile saves) --------------------------------------------------------

PROFILE = (
    "domains: \n"
    "  local: \n"
    "    progression_shared: \n"
    "      graphs: \n"
    "      - name: sdu_upgrades\n"
    "        nodes: \n"
    "        - name: Ammo_A\n"
    "          points_spent: 5\n"
    "        - name: Ammo_B\n"
    "          points_spent: 10\n"
    "      - name: other_graph\n"
    "        nodes: \n"
    "        - name: X\n"
    "          points_spent: 1000\n"
    "      point_pools: \n"
    "        echotokenprogresspoints: 140\n"
    "        othershared: 7\n"
    "progression: \n"
    "  point_pools: \n"
    "    characterprogresspoints: 9\n"
)


def test_shared_pool_patch_changes_exactly_one_line_and_reverses(save):
    new = save.set_shared_point_pool(PROFILE, "echotokenprogresspoints", 1000)
    assert save.changed_lines(PROFILE, new) == [
        (16, "        echotokenprogresspoints: 140", "        echotokenprogresspoints: 1000")]
    assert save.set_shared_point_pool(new, "echotokenprogresspoints", 140) == PROFILE
    crlf = PROFILE.replace("\n", "\r\n")
    assert save.set_shared_point_pool(crlf, "othershared", 8).count("\r\n") == crlf.count("\r\n")


def test_shared_pool_refusals(save):
    with pytest.raises(SaveError, match="echotokenprogresspoints, othershared"):
        save.set_shared_point_pool(PROFILE, "nope", 1)
    with pytest.raises(SaveError, match="no shared point pool"):
        save.set_shared_point_pool(PROFILE, "characterprogresspoints", 1)     # top-level pool is out of reach
    with pytest.raises(SaveError, match="no domains"):
        save.set_shared_point_pool(SYNTH, "echotokenprogresspoints", 1)
    for bad, needle in ((-1, "from 0"), (2 ** 31, "from 0"), ("5", "integer"), (True, "integer")):
        with pytest.raises(SaveError, match=needle):
            save.set_shared_point_pool(PROFILE, "echotokenprogresspoints", bad)
    with pytest.raises(SaveError, match="plain integer"):
        save.set_shared_point_pool(PROFILE.replace("140", "abc"), "echotokenprogresspoints", 1)
    assert save.set_shared_point_pool(PROFILE, "echotokenprogresspoints", 2 ** 31 - 1)


def test_shared_pool_report_available_math(save):
    r = save.shared_pool_report(PROFILE)
    assert (r["value"], r["spent"], r["available"]) == (140, 15, 125)       # other_graph is not counted
    r = save.shared_pool_report(save.set_shared_point_pool(PROFILE, "echotokenprogresspoints", 1000))
    assert (r["value"], r["available"]) == (1000, 985)
    assert save.shared_pool_report(SYNTH) is None
