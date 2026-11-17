"""Tests for bl4forge.tools.save_history. Synthetic saves only, sealed with a THROWAWAY key (never a game key)."""
from __future__ import annotations

import math
import os

import pytest

from bl4forge.core.errors import SaveError
from bl4forge.modules.save import _container
from bl4forge.tools import save_history as sh

KEY = bytes(range(32))              # throwaway, same convention as tests/save_helpers.py
OTHER_KEY = bytes(range(1, 33))
STEAM_ID = "76561198000000000"

# One "game load": the style the game writes (trailing `key: ` spaces, lists at the key's indent, LF).
LOAD_1 = (
    "state: \n"
    "  char_name: Hunter\n"
    "  class: Char_ExoSoldier\n"
    "  experience: \n"
    "  - type: character\n"
    "    level: 22\n"
    "    points: 355313\n"
    "  - type: specialization\n"
    "    level: 3\n"
    "    points: 1200\n"
    "  inventory: \n"
    "    items: \n"
    "      backpack: \n"
    "        slot_0: \n"
    "          serial: '@Ugabc'\n"
    "          state_flags: 1\n"
    "    equipped_inventory: \n"
    "      equipped: \n"
    "        slot_3: \n"
    "        - serial: '@Ugdef'\n"
    "          flags: 1\n"
    "  currencies: \n"
    "    cash: 1000163543\n"
    "    eridium: 1000001124\n"
    "  missions: \n"
    "    - name: mission_main_01\n"
    "      status: completed\n"
    "    - name: mission_side_07\n"
    "      status: active\n"
    "  discovered: [zone_a, zone_b]\n"
    "  fov_scale: 1.50\n"
    "  hardcore: false\n"
    "  last_vendor: ~\n"
    "  lostloot: \n"
    "    items: \n"
    "    - serial: '@Ughij'\n"
    "      in_machine: true\n"
    "    slots: 6\n"
    "stats: \n"
    "  getcash: 0\n"
)

# The next "game load": the SAME values re-serialised. Key order, quoting, list indentation, trailing
# spaces, number spelling, flow vs block lists and line endings all differ.
LOAD_2 = "\r\n".join([
    "stats:",
    "  getcash: 0",
    "state:",
    "  currencies:",
    "    eridium: 1000001124",
    "    cash: 1000163543",
    "  class: 'Char_ExoSoldier'",
    '  char_name: "Hunter"',
    "  hardcore: False",
    "  last_vendor: null",
    "  fov_scale: 1.5",
    "  discovered:",
    "  - zone_a",
    '  - "zone_b"',
    "  experience:",
    "    - level: 22",
    "      type: character",
    "      points: 355313",
    "    - points: 1200",
    "      level: 3",
    '      type: "specialization"',
    "  missions:",
    "  - status: completed",
    "    name: mission_main_01",
    "  - name: 'mission_side_07'",
    "    status: active",
    "  lostloot:",
    "    slots: 6",
    "    items:",
    "      - in_machine: True",
    '        serial: "@Ughij"',
    "  inventory:",
    "    equipped_inventory:",
    "      equipped:",
    "        slot_3:",
    "          - flags: 1",
    "            serial: '@Ugdef'",
    "    items:",
    "      backpack:",
    "        slot_0:",
    "          state_flags: 1",
    '          serial: "@Ugabc"',
]) + "\r\n"


def _seal(text: str, key: bytes = KEY) -> bytes:
    return _container.encrypt(text.encode("utf-8"), key, "ps5")


@pytest.fixture
def store(tmp_path):
    return sh.Store.init(str(tmp_path))


def _snap(store, tmp_path, name, text, message=""):
    path = tmp_path / name
    path.write_bytes(_seal(text))
    return sh.take_snapshot(store, str(path), KEY, message)["id"]


# ---- the two required properties ------------------------------------------------------------------

def test_two_game_loads_with_same_values_give_an_empty_diff(store, tmp_path):
    a = _snap(store, tmp_path, "load1.sav", LOAD_1, "first load")
    b = _snap(store, tmp_path, "load2.sav", LOAD_2, "second load")
    assert (tmp_path / "load1.sav").read_bytes() != (tmp_path / "load2.sav").read_bytes()
    assert store.meta(a)["yaml_sha256"] != store.meta(b)["yaml_sha256"]      # plaintexts differ too
    assert store.read_normalized(a) == store.read_normalized(b)              # normalized forms do not
    assert sh.diff_snapshots(store, a, b) == []
    assert store.meta(b)["same_as"] == a


def test_a_real_value_change_is_reported_exactly(store, tmp_path, capsys, monkeypatch):
    changed = LOAD_2.replace("cash: 1000163543", "cash: 1000200000")
    assert changed != LOAD_2
    a = _snap(store, tmp_path, "load1.sav", LOAD_1)
    b = _snap(store, tmp_path, "load2.sav", changed)
    assert sh.diff_snapshots(store, a, b) == [
        sh.Change("changed", ("state", "currencies", "cash"), 1000163543, 1000200000)]
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    assert sh.main(["diff", str(a), str(b)]) == 1
    out = capsys.readouterr().out
    assert "1 change under 1 top-level key: state" in out
    assert "~ state.currencies.cash: 1000163543 -> 1000200000" in out
    assert store.meta(b)["same_as"] is None


# ---- list handling ---------------------------------------------------------------------------------

def test_list_elements_are_matched_by_stable_id():
    new = (LOAD_1.replace("      status: active", "      status: completed")
           .replace("    level: 22", "    level: 23")
           .replace("  discovered:", "    - name: mission_side_09\n      status: active\n  discovered:"))
    changes = sh.diff_trees(sh.parse_yaml(LOAD_1), sh.parse_yaml(new))
    assert changes == [
        sh.Change("changed", ("state", "experience", "[type=character]", "level"), 22, 23),
        sh.Change("changed", ("state", "missions", "[name=mission_side_07]", "status"), "active", "completed"),
        sh.Change("added", ("state", "missions", "[name=mission_side_09]"), None,
                  {"name": "mission_side_09", "status": "active"}),
    ]
    assert changes[1].where == "state.missions[name=mission_side_07].status"


def test_lists_without_ids_report_counts_or_positions():
    a = sh.parse_yaml("rolls:\n- {a: 1}\n- {a: 1}\n")
    assert sh.diff_trees(a, sh.parse_yaml("rolls:\n- {a: 1}\n- {a: 1}\n- {a: 2}\n")) == [
        sh.Change("count", ("rolls",), 2, 3)]
    assert sh.diff_trees(a, sh.parse_yaml("rolls:\n- {a: 1}\n- {a: 5}\n")) == [
        sh.Change("changed", ("rolls", "[1]", "a"), 1, 5)]


def test_scalar_lists_compare_as_sets():
    a = sh.parse_yaml("discovered: [zone_a, zone_b]\n")
    b = sh.parse_yaml("discovered: [zone_a, zone_c]\n")
    assert sh.diff_trees(a, b) == [sh.Change("removed", ("discovered", "[zone_b]"), "zone_b", None),
                                   sh.Change("added", ("discovered", "[zone_c]"), None, "zone_c")]


def test_reorder_is_reported_unless_ignored():
    a = sh.parse_yaml("missions:\n- name: x\n- name: y\n")
    b = sh.parse_yaml("missions:\n- name: y\n- name: x\n")
    assert sh.diff_trees(a, b) == [sh.Change("reordered", ("missions",), 2, 2)]
    assert sh.diff_trees(a, b, ignore_order=True) == []


def test_ignore_paths_and_float_digits():
    a = sh.parse_yaml("stats:\n  playtime: 10\nscale: 0.30000001\n")
    b = sh.parse_yaml("stats:\n  playtime: 99\nscale: 0.3\n")
    assert len(sh.diff_trees(a, b)) == 2
    assert sh.diff_trees(a, b, ignore=["stats"], float_digits=6) == []


def test_int_and_float_spellings_of_one_number_do_not_diff():
    assert sh.diff_trees(sh.parse_yaml("x: 1\n"), sh.parse_yaml("x: 1.0\n")) == []
    assert sh.diff_trees(sh.parse_yaml("x: 1\n"), sh.parse_yaml("x: true\n")) != []


# ---- normalization ---------------------------------------------------------------------------------

def test_canonical_form_round_trips_and_is_deterministic():
    tree = {
        "plain": "x", "quote": "it's", "nl": "a\nb", "uni": "Zo\u00eb \u2603", "astral": "a\n\U0001F600",
        "empty": "", "looks_int": "007", "looks_bool": "true", "odd key: #1": 1,
        "f": [0.1, 1e-05, 1e20, 100.0, float("inf"), float("-inf")],
        "i": [-3, 0, 2 ** 63 - 1], "b": [True, False, None],
        "nested": [[1, [2]], {}, [], {"k": {"deep": [{"x": 1, "y": [1, 2]}]}}],
    }
    canon = sh.dump_canonical(tree)
    assert sh.parse_yaml(canon) == tree
    assert sh.dump_canonical(sh.parse_yaml(canon)) == canon
    assert math.isnan(sh.parse_yaml(sh.dump_canonical({"n": float("nan")}))["n"])


def test_the_game_style_is_parsed_into_the_expected_tree():
    tree = sh.parse_yaml(LOAD_1)
    assert tree["state"]["experience"][0] == {"type": "character", "level": 22, "points": 355313}
    assert tree["state"]["inventory"]["equipped_inventory"]["equipped"]["slot_3"] == [
        {"serial": "@Ugdef", "flags": 1}]
    assert tree["state"]["lostloot"] == {"items": [{"serial": "@Ughij", "in_machine": True}], "slots": 6}
    assert tree["state"]["last_vendor"] is None and tree["state"]["fov_scale"] == 1.5


@pytest.mark.parametrize("text", [
    "a: &x 1\nb: *x\n",          # anchors / aliases
    "a: !tag 1\n",               # tags
    "a: |\n  text\n",            # block scalar
    "a: 'unterminated\n",        # multi-line quoted
    "a: 1\na: 2\n",              # duplicate key
    "a:\n\t- 1\n",               # tab indentation
    "a: 1\n  b: 2\n",            # stray indentation
])
def test_yaml_outside_the_subset_is_refused(text):
    with pytest.raises(sh.HistoryError):
        sh.parse_yaml(text)


# ---- store, CLI and key handling ---------------------------------------------------------------------

def test_cli_end_to_end_and_restore_is_byte_exact(tmp_path, capsys, monkeypatch):
    (tmp_path / "load1.sav").write_bytes(_seal(LOAD_1))
    (tmp_path / "load2.sav").write_bytes(_seal(LOAD_2))
    keyfile = tmp_path / "ps5.key"
    keyfile.write_text("0x" + KEY.hex() + "\n")
    assert sh.main(["init", str(tmp_path)]) == 0
    assert sh.main(["init", str(tmp_path)]) == 2                          # already exists
    monkeypatch.chdir(tmp_path)
    assert sh.main(["snapshot", "load1.sav", "--key-file", str(keyfile), "-m", "before vault run"]) == 0
    assert sh.main(["snapshot", "load2.sav", "--key-file", str(keyfile), "-m", "after reload"]) == 0
    capsys.readouterr()
    assert sh.main(["diff", "1", "latest"]) == 0
    assert "no semantic changes" in capsys.readouterr().out
    assert sh.main(["log"]) == 0
    log = capsys.readouterr().out
    assert "before vault run" in log and "after reload" in log and "same values as 0001" in log
    out_file = tmp_path / "restored.sav"
    assert sh.main(["restore", "latest~1", "-o", str(out_file)]) == 0
    assert out_file.read_bytes() == (tmp_path / "load1.sav").read_bytes()
    assert sh.main(["restore", "1", "-o", str(out_file)]) == 2           # refuses to overwrite
    assert sh.main(["restore", "2", "-o", str(out_file), "--force"]) == 0
    assert out_file.read_bytes() == (tmp_path / "load2.sav").read_bytes()


def test_key_is_never_written_to_the_store_or_printed(tmp_path, capsys, monkeypatch):
    (tmp_path / "load1.sav").write_bytes(_seal(LOAD_1))
    keyfile = tmp_path / "ps5.key"
    keyfile.write_bytes(KEY)                                              # raw 32-byte form
    sh.main(["init", str(tmp_path)])
    monkeypatch.chdir(tmp_path)
    assert sh.main(["snapshot", "load1.sav", "--key-file", str(keyfile)]) == 0
    sh.main(["log", "--json"])
    printed = capsys.readouterr()
    for needle in (KEY.hex(), KEY.hex().upper()):
        assert needle not in printed.out and needle not in printed.err
    for root, _dirs, files in os.walk(tmp_path / sh.STORE_DIRNAME):
        for name in files:
            with open(os.path.join(root, name), "rb") as fh:
                data = fh.read()
            assert KEY not in data
            assert KEY.hex().encode() not in data.lower()


def test_wrong_key_stores_nothing(store, tmp_path):
    path = tmp_path / "other.sav"
    path.write_bytes(_seal(LOAD_1, OTHER_KEY))
    with pytest.raises(SaveError):
        sh.take_snapshot(store, str(path), KEY, "should fail")
    assert store.ids() == [] and os.listdir(store.snap_dir) == []


def test_key_file_formats(tmp_path):
    raw = tmp_path / "raw.key"
    raw.write_bytes(KEY)
    spaced = tmp_path / "spaced.key"
    spaced.write_text(" ".join(KEY.hex()[i:i + 8] for i in range(0, 64, 8)) + "\r\n")
    assert sh.load_key(str(raw)) == KEY and sh.load_key(str(spaced)) == KEY
    bad = tmp_path / "bad.key"
    bad.write_text("deadbeef")
    with pytest.raises(sh.HistoryError) as err:
        sh.load_key(str(bad))
    assert "deadbeef" not in str(err.value)


def test_pc_saves_need_a_steam_id(tmp_path, monkeypatch):
    (tmp_path / "pc.sav").write_bytes(
        _container.encrypt(LOAD_1.encode(), _container.pc_key(KEY, STEAM_ID), "pc"))
    keyfile = tmp_path / "pc_base.key"
    keyfile.write_text(KEY.hex())
    sh.main(["init", str(tmp_path)])
    monkeypatch.chdir(tmp_path)
    assert sh.main(["snapshot", "pc.sav", "--key-file", str(keyfile), "--platform", "pc"]) == 2
    assert sh.main(["snapshot", "pc.sav", "--key-file", str(keyfile), "--platform", "pc",
                    "--steam-id", STEAM_ID]) == 0


def test_resolve_and_tamper_detection(store, tmp_path):
    a = _snap(store, tmp_path, "a.sav", LOAD_1)
    b = _snap(store, tmp_path, "b.sav", LOAD_2)
    assert (store.resolve("latest"), store.resolve("HEAD~1"), store.resolve("0001")) == (b, a, a)
    with pytest.raises(sh.HistoryError):
        store.resolve("7")
    with pytest.raises(sh.HistoryError):
        store.resolve("latest~5")
    with open(os.path.join(store.snap_dir, "%04d.yaml" % a), "a", encoding="utf-8") as fh:
        fh.write("extra: 1\n")
    with pytest.raises(sh.HistoryError):
        store.read_normalized(a)
