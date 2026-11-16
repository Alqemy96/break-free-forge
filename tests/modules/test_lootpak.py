"""Tests for the `lootpak` cell: config validation, leaf location (binary order), the planner, the decode-diff
gate, write protection, the subprocess adapter, the cell/CLI wiring, and two GOLDEN builds against the real
files (skipped when the private tools or the modwork folder are absent).

Everything except the two golden tests runs on a fake tool set (tests/lootpak_helpers.py), no game files.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from bl4forge.core.config import Config
from bl4forge.core.errors import ConfigError, LootPakError
from bl4forge.core.forge import Forge
from bl4forge.core.module import ModuleContext, conformance_problems
from bl4forge.core.ports import LootPakPort
from bl4forge.modules.lootpak import MODULE as LootPakModule
from bl4forge.modules.lootpak import _build, _config, _decode, _guard, _leaves, _locate, _plan, _tools
from tests.lootpak_helpers import (BINOFF, PROBS_BINARY, FakeTools, config_text, make_raw, render_decode,
                                   write_base)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples" / "lootpak"


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse(tmp_path, body, **kw):
    paths = write_base(tmp_path)
    return paths, _config.parse_config(config_text(paths, body), **kw)


def plan_of(tmp_path, body, tools=None, overrides=None):
    paths = write_base(tmp_path, overrides)
    cfg = _config.parse_config(config_text(paths, body))
    tools = tools or FakeTools()
    return cfg, tools, _plan.make_plan(cfg, tools, tmp_path / "scratch")


# ------------------------------------------------------------------------------------ config validation
def test_config_parses_and_names_rows_and_fields(tmp_path):
    _, cfg = parse(tmp_path, "[enemydrops.Elite]\nguns_probability = 0.4\n[enemydrops.Elite.rarity_modifier]\n"
                             "raremodifier = 25\n[rarity_balance.Common]\nbase_weight = 0.005\n")
    assert [(s.section, s.row, s.field, s.value) for s in cfg.settings] == [
        ("enemydrops", "Elite", "guns_probability", 0.4), ("enemydrops", "Elite", "rarity_modifier.raremodifier", 25.0),
        ("rarity_balance", "Common", "base_weight", 0.005)]
    assert cfg.pak.seed == 2190688979 and cfg.pak.mount == "../../../" and cfg.pak.name.endswith(".pak")


def test_config_relative_paths_resolve_against_modwork(tmp_path):
    text = ('[base]\nraw = "out1/a.raw"\ninventory = "out1/i.ncs"\nreference_pak = "out3/p.pak"\n')
    cfg = _config.parse_config(text, modwork=tmp_path)
    assert cfg.base.raw == tmp_path / "out1" / "a.raw"


@pytest.mark.parametrize("body, needle", [
    ("[enemydrops.Elite]\nbogus_probability = 0.1\n", "unknown field"),
    ("[nosuchsection.X]\na = 1\n", "unknown section"),
    ("[enemydrops.Elite]\nguns_probability = 1.5\n", "out of range"),
    ("[enemydrops.Elite]\nguns_probability = -0.1\n", "out of range"),
    ("[enemydrops.Elite]\nguns_probability = \"0.4\"\n", "must be a number"),
    ("[enemydrops.Elite]\nguns_probability = true\n", "must be a number"),
    ("[enemydrops.Elite]\nguns_probability = 0.1234567\n", "6 decimals"),
    ("[enemydrops.Elite]\nguns_probability = 0.4\n[enemydrops.elite]\nguns_probability = 0.5\n", "duplicate"),
    ("[enemydrops.Elite]\nguns_probability = 0.4\nguns_probability = 0.5\n", "cannot parse"),
    ("[enemydrops]\n", "must contain rows"),
    ("[enemydrops.Elite]\n", "table of fields"),
    ("[rarity_balance.Common]\nbase_weight = nan\n", "out of range"),
])
def test_config_rejects(tmp_path, body, needle):
    paths = write_base(tmp_path)
    with pytest.raises(ConfigError) as ex:
        _config.parse_config(config_text(paths, body))
    assert needle in str(ex.value)


def test_config_requires_base_and_rejects_unknown_base_key():
    with pytest.raises(ConfigError, match=r"\[base\] is required"):
        _config.parse_config("[meta]\nname='x'\n")
    with pytest.raises(ConfigError, match="unknown key"):
        _config.parse_config('[base]\nraw="a"\ninventory="b"\nreference_pak="c"\nsave_key="x"\n')


def test_config_unknown_row_field_and_pool_checks_against_the_base(tmp_path):
    with pytest.raises(ConfigError, match="unknown row 'Nobody'"):
        plan_of(tmp_path / "a", "[enemydrops.Nobody]\nguns_probability = 0.25\n")
    # Normal has no rarity_modifier struct in the base: v1 never inserts one
    with pytest.raises(ConfigError, match="never inserts"):
        plan_of(tmp_path / "b", "[enemydrops.Normal.rarity_modifier]\nraremodifier = 25\n")
    # 0.33 is not a pool string: no add-strings in v1
    with pytest.raises(ConfigError, match="not in the string pool"):
        plan_of(tmp_path / "c", "[enemydrops.Elite]\nguns_probability = 0.33\n")
    # rows match case-insensitively but are reported as named in the base
    _, _, plan = plan_of(tmp_path / "d", "[enemydrops.elite]\nguns_probability = 0.25\n")
    assert plan.changes[0].label == "enemydrops.Elite.guns_probability"


# ------------------------------------------------------------------------------------ spawnbalance section
@pytest.mark.parametrize("body, needle", [
    ('[spawnbalance.Duo_add1]\ntwoplayers_constant = 2\n', "unknown field"),
    ('[spawnbalance.Duo_add1.twoplayers]\nconstant = 2\n', "unknown field"),
    ('[spawnbalance.Duo_add1]\nthreeplayers_constant = 2\n', "unknown field"),
    ('[spawnbalance.Duo_add1]\nfourplayers_constant = 2\n', "unknown field"),
    ('[spawnbalance.Duo_add1]\noneplayer_postscale = 2\n', "unknown field"),
    ('[spawnbalance.Duo_add1.oneplayer]\npostscale = 2\n', "unknown field"),
    ('[spawnbalance.Duo_add1.oneplayer.datatablevalue]\nrowname = 2\n', "unknown field"),
    ('[spawnbalance.Duo_add1]\noneplayer_constant = -1\n', "out of range"),
    ('[spawnbalance.Duo_add1]\noneplayer_constant = 21\n', "out of range"),
    ('[spawnbalance.Duo_add1]\noneplayer_constant = "2"\n', "must be a number"),
    ('[spawnbalance.Duo_add1]\noneplayer_constant = 2\n[spawnbalance.duo_add1.oneplayer]\nconstant = 3\n', "duplicate"),
])
def test_spawnbalance_validation_rejects_everything_but_oneplayer_constant(tmp_path, body, needle):
    paths = write_base(tmp_path)
    with pytest.raises(ConfigError) as ex:
        _config.parse_config(config_text(paths, body))
    assert needle in str(ex.value)


def test_spawnbalance_accepts_the_flat_and_nested_spelling_and_quoted_row_names(tmp_path):
    _, cfg = parse(tmp_path, '[spawnbalance."2P+_add1_&_4P_add2"]\noneplayer_constant = 2.0\n'
                             '[spawnbalance.Default.oneplayer]\nconstant = 1\n')
    got = [(s.section, s.row, s.field, s.value) for s in cfg.settings]
    assert got == [("spawnbalance", "2P+_add1_&_4P_add2", "oneplayer.constant", 2.0),
                   ("spawnbalance", "Default", "oneplayer.constant", 1.0)]
    assert _config.SECTIONS["spawnbalance"][0] == "table_playercountspawnbalancedata"
    assert set(_config.SECTIONS["spawnbalance"][1]) == {"oneplayer.constant"}


def test_spawnbalance_plan_edits_only_the_oneplayer_constant_and_finds_it_past_the_true_leaf(tmp_path):
    cfg, tools, plan = plan_of(tmp_path, "[spawnbalance.Duo_add1]\noneplayer_constant = 2\n"
                                         "[spawnbalance.SoloDefault]\noneplayer_constant = 3\n")
    model = json.loads(make_raw())
    tbl = [t for t in model["tables"] if t["key"] == "table_playercountspawnbalancedata"][0]
    want = {r["name"]: model["leaves"][dict(r["fields"])["oneplayer.constant"]]["bitpos"] for r in tbl["rows"]}
    assert {c.row: c.bitpos for c in plan.changes} == want
    assert {c.row: (c.path, c.old_text, c.new_text) for c in plan.changes} == {
        "Duo_add1": ("oneplayer.constant", "1.000000", "2.000000"),
        "SoloDefault": ("oneplayer.constant", "0.000000", "3.000000")}
    # the co-op columns and every other leaf are not in the plan
    assert all(c.path == "oneplayer.constant" for c in plan.changes)
    # the probe told the four identical (0.0 / 1.0) constants apart: the plan line is the oneplayer one
    assert all(c.prefix.strip() == "constant:" for c in plan.changes)


def test_spawnbalance_build_gate_passes_with_exactly_one_changed_line(tmp_path):
    paths = write_base(tmp_path)
    cfg = _config.parse_config(config_text(paths, "[spawnbalance.Duo_add1]\noneplayer_constant = 2\n"))
    res = _build.build(cfg, tmp_path / "out", FakeTools())
    assert len(res.diff) == 1 and res.diff[0][1].strip() == "constant: 1.000000"
    assert res.diff[0][2].strip() == "constant: 2.000000"


def test_spawnbalance_refuses_a_row_whose_value_is_not_in_the_pool(tmp_path):
    with pytest.raises(ConfigError, match="not in the string pool"):
        plan_of(tmp_path, "[spawnbalance.Duo_add1]\noneplayer_constant = 2.5\n")


def test_anchor_skips_only_boolean_leaves_between_struct_and_first_row(tmp_path):
    raw = json.loads(make_raw())
    i = next(n for n, lf in enumerate(raw["leaves"]) if raw["pool"][lf["raw"]] == "true")
    raw["leaves"][i]["raw"] = raw["pool"].index("none")        # a non-boolean leaf in that slot: refuse, don't guess
    paths = write_base(tmp_path)
    paths["raw"].write_bytes(json.dumps(raw).encode())
    cfg = _config.parse_config(config_text(paths, "[spawnbalance.Duo_add1]\noneplayer_constant = 2\n"))
    with pytest.raises(LootPakError, match="cannot anchor"):
        _plan.make_plan(cfg, FakeTools(), tmp_path / "scratch")


# ------------------------------------------------------------------------------------ decode parser
def test_decode_parser_reads_paths_prefixes_and_odd_array_closers():
    text = render_decode(json.loads(make_raw()))
    tbl = _decode.parse_decode(text)["table_enemydrops"][0]
    elite = [r for r in tbl.rows if r.name == "Elite"][0]
    paths = [lf.path for lf in elite.leaves]
    assert "rarity_modifier.commonmodifier" in paths and paths == sorted(paths)       # alphabetical, like the real decode
    assert elite.get("guns_probability").prefix.endswith("guns_probability: ")
    odd = ("File: x\n    table_x = {\n      data: [{\n          row_name: A\n          row_value: {\n"
           "            w: [, {\n                value: {\n                  constant: 1.000000\n"
           "                }\n              }, ]\n            n: 2.000000\n          }\n        }]\n"
           "      gbx_ue_data_table: X\n      row_struct: Asset'/S.S'\n    }\n")
    row = _decode.parse_decode(odd)["table_x"][0].rows[0]
    assert [lf.path for lf in row.leaves] == ["w[1].value.constant", "n"]
    with pytest.raises(LootPakError, match="unclosed"):
        _decode.parse_decode("    table_x = {\n      data: [{\n")


def test_leaf_log_and_pool_parsers():
    log = _leaves.parse_leaf_log("BINOFF 12\nLEAF bitpos=5 bits=13 raw=2 mapped=2 val=a b\n")
    assert log.binoff == 12 and log.leaves[0].val == "a b"
    with pytest.raises(LootPakError, match="remapped"):
        _leaves.parse_leaf_log("BINOFF 1\nLEAF bitpos=5 bits=13 raw=2 mapped=3 val=x\n")
    with pytest.raises(LootPakError):
        _leaves.parse_leaf_log("nothing here")
    assert _leaves.parse_pool("0\tx\n1\ty\n") == {0: "x", 1: "y"}


# ------------------------------------------------------------------------------------ binary leaf order
def test_binary_leaf_order_is_not_decode_order_and_planner_follows_the_binary(tmp_path):
    raw = make_raw()
    model = json.loads(raw)
    chump = [r for r in model["tables"][0]["rows"] if r["name"] == "Chump"][0]
    by_field = dict(chump["fields"])
    pos = {f: model["leaves"][i]["bitpos"] for f, i in by_field.items()}
    decode_order = [f for f, _ in chump["fields"] if f.endswith("_probability") and f != "currencyorammo_probability"]
    assert decode_order != PROBS_BINARY, "the fake must be adversarial: decode order differs from binary order"
    assert [f for f in sorted(PROBS_BINARY, key=pos.get)] == PROBS_BINARY
    body = "[enemydrops.Chump]\n" + "".join("%s = 0.25\n" % f for f in PROBS_BINARY)
    _, _, plan = plan_of(tmp_path, body)
    got = {c.path: c.bitpos for c in plan.changes}
    assert got == {f: pos[f] for f in PROBS_BINARY}, "every field must be mapped to ITS binary leaf"
    assert [c.path for c in plan.changes] == PROBS_BINARY                # sorted by bit position = binary order


def test_leaves_with_identical_values_are_told_apart_by_the_probe(tmp_path):
    # Elite uncommon, legendary and pearl all start at 5.000000 (the same pool index)
    body = "[enemydrops.Elite.rarity_modifier]\nuncommonmodifier = 7\nlegendarymodifier = 9\npearlmodifier = 8\n"
    _, _, plan = plan_of(tmp_path, body)
    model = json.loads(make_raw())
    elite = [r for r in model["tables"][0]["rows"] if r["name"] == "Elite"][0]
    want = {f: model["leaves"][i]["bitpos"] for f, i in elite["fields"] if f.startswith("rarity_modifier.")}
    for c in plan.changes:
        assert c.bitpos == want[c.path], c.path
    assert {c.path: c.new_text for c in plan.changes} == {
        "rarity_modifier.uncommonmodifier": "7.000000", "rarity_modifier.legendarymodifier": "9.000000",
        "rarity_modifier.pearlmodifier": "8.000000"}


# ------------------------------------------------------------------------------------ planner (fake tools)
def test_plan_is_pure_planning_and_reports_noops(tmp_path):
    paths = write_base(tmp_path)
    before = {k: sha(v) for k, v in paths.items()}
    body = ("[enemydrops.Chump]\nguns_probability = 0.25\nclassmods_probability = 0.05\n"
            "[rarity_balance.Common]\nbase_weight = 0.005\n[difficulty_standard.Normal]\nlootluck = 100\n")
    cfg = _config.parse_config(config_text(paths, body))
    tools = FakeTools()
    plan = _plan.make_plan(cfg, tools, tmp_path / "scratch")
    assert {c.label for c in plan.changes} == {"enemydrops.Chump.guns_probability", "rarity_balance.Common.base_weight"}
    assert set(plan.unchanged) == {"enemydrops.Chump.classmods_probability",
                                   "difficulty_standard.Normal.lootluck"}
    assert all(c.op == "set_leaf" for c in plan.changes)
    assert [c.bitpos for c in plan.changes] == sorted(c.bitpos for c in plan.changes)
    text = "\n".join(_plan.format_plan(plan))
    assert "0.050000 -> 0.250000" in text and "keep" in text
    assert not [c for c in tools.calls if c[0] in ("mkpak", "extract")]
    assert {k: sha(v) for k, v in paths.items()} == before                 # the base is untouched
    assert not (tmp_path / "base" / "out").exists()


def test_plan_triples_carry_old_and_new_pool_indexes(tmp_path):
    _, _, plan = plan_of(tmp_path, "[enemydrops.Elite]\nguns_probability = 0.6\n")
    c = plan.changes[0]
    pool = json.loads(make_raw())["pool"]
    assert (c.old_text, c.new_text) == ("0.100000", "0.600000")
    assert c.triple == (c.bitpos, 13, pool.index("0.100000"), pool.index("0.600000"))


def test_a_string_the_pool_holds_twice_is_not_a_change(tmp_path):
    paths = write_base(tmp_path)
    model = json.loads(paths["raw"].read_bytes())
    model["pool"].append("0.150000")                                  # a duplicate string, like the real pool's 0.14
    dup = len(model["pool"]) - 1
    chump = [r for r in model["tables"][0]["rows"] if r["name"] == "Chump"][0]
    model["leaves"][dict(chump["fields"])["classmods_probability"]]["raw"] = dup
    paths["raw"].write_bytes(json.dumps(model).encode())
    cfg = _config.parse_config(config_text(paths, "[enemydrops.Chump]\nclassmods_probability = 0.15\n"))
    plan = _plan.make_plan(cfg, FakeTools(), tmp_path / "scratch")
    assert plan.changes == () and plan.unchanged == ("enemydrops.Chump.classmods_probability",)


def test_set_leaf_value_is_snapped_to_ncs_spelling(tmp_path):
    _, _, plan = plan_of(tmp_path, "[difficulty_standard.Normal]\nlootluck = 5\n")      # '5.000000' exists in the pool
    assert plan.changes[0].new_text == "5.000000"


# ------------------------------------------------------------------------------------ build + gate (fake tools)
def build_fake(tmp_path, body, tools=None, name="t"):
    paths = write_base(tmp_path)
    cfg = _config.parse_config(config_text(paths, body, name))
    tools = tools or FakeTools()
    lines = []
    res = _build.build(cfg, tmp_path / "newout", tools, lines.append)
    return paths, cfg, tools, res, lines


BODY = "[enemydrops.Elite]\nguns_probability = 0.6\nclassmods_probability = 0.15\n[rarity_balance.Common]\nbase_weight = 0.005\n"


def test_build_end_to_end_writes_pak_manifest_regen_and_prints_plan_first(tmp_path):
    paths, cfg, tools, res, lines = build_fake(tmp_path, BODY)
    out = tmp_path / "newout"
    assert lines[0].startswith("inputs hashed") and lines[1].startswith("plan t: 3 set_leaf")
    assert any(l.startswith("gate passed") for l in lines)
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert man["inputs"]["raw"]["sha256"] == sha(paths["raw"]) and man["inputs_unchanged"] is True
    assert man["outputs"]["pak"]["sha256"] == sha(res.pak_path) == res.pak_sha256
    assert man["outputs"]["pak"]["bytes"] == res.pak_path.stat().st_size
    assert len(man["plan"]) == len(man["diff"]) == 3 and man["gate"].startswith("pass")
    regen = (out / "REGEN.txt").read_text(encoding="utf-8")
    assert "set-bits" in regen and "mkpak" in regen and res.pak_sha256 in regen and "2190688979" in regen
    for c in res.plan.changes:
        assert "%d %d %d %d" % c.triple in regen
    assert (out / "decoded_table0.txt").is_file() and (out / "diff_table0_vs_base.txt").is_file()
    # the exact mkpak recipe: out, mount, seed, reference pak, table0 then inventory
    mk = [c for c in tools.calls if c[0] == "mkpak"][0][1]
    assert mk == ("pakchunk100-ps5_P.pak", "../../../", 2190688979, "ref.pak", (
        "Engine/Content/_NCS/Nexus-Data-gbx_ue_data_table0.ncs",
        "Engine/Content/_NCS/Nexus-Data-inventory_container0.ncs"))
    # nothing was written outside the new folder, and the base is unchanged
    assert sha(paths["raw"]) == man["inputs"]["raw"]["sha256"]
    assert sorted(p.name for p in (tmp_path / "base").iterdir()) == ["inv.ncs", "ref.pak", "t0.raw"]


def test_build_with_empty_plan_reproduces_the_base_table(tmp_path):
    paths, cfg, tools, res, _ = build_fake(tmp_path, "[enemydrops.Chump]\nclassmods_probability = 0.05\n")
    assert not res.plan.changes and res.diff == []
    assert res.raw_sha256 == sha(paths["raw"])


def test_gate_fails_on_an_extra_change_and_rejects_the_pak(tmp_path):
    paths = write_base(tmp_path)
    cfg = _config.parse_config(config_text(paths, BODY))
    with pytest.raises(LootPakError, match="UNPLANNED change"):
        _build.build(cfg, tmp_path / "newout", FakeTools(sneak_change=True))
    out = tmp_path / "newout"
    assert not (out / "manifest.json").exists() and not (out / "REGEN.txt").exists()
    assert (out / "pakchunk100-ps5_P.pak.REJECTED").exists() and not (out / "pakchunk100-ps5_P.pak").exists()
    assert "UNPLANNED" in (out / "FAILED.txt").read_text(encoding="utf-8")


def test_gate_problems_unit(tmp_path):
    cfg, tools, plan = plan_of(tmp_path, "[enemydrops.Elite]\nguns_probability = 0.6\n")
    base = plan.base_decode
    c = plan.changes[0]
    lines = base.split("\n")
    good = list(lines)
    good[c.line] = c.new_line
    assert _build.gate_problems(plan, "\n".join(good))[0] == []
    # the planned change did not happen
    assert "planned change did not happen" in _build.gate_problems(plan, base)[0][0]
    # right line, wrong value
    wrong = list(lines)
    wrong[c.line] = c.prefix + "0.400000"
    assert "planned" in _build.gate_problems(plan, "\n".join(wrong))[0][0]
    # an additional line changes
    extra = list(good)
    extra[c.line + 1] = extra[c.line + 1] + "9"
    assert any("UNPLANNED" in p for p in _build.gate_problems(plan, "\n".join(extra))[0])
    # a line-count change
    assert "line count" in _build.gate_problems(plan, base + "x\n")[0][0]


def test_config_hash_expectation_is_enforced(tmp_path):
    paths = write_base(tmp_path)
    text = config_text(paths, "[enemydrops.Elite]\nguns_probability = 0.6\n").replace(
        "[base]\n", '[base]\nraw_sha256 = "%s"\n' % ("0" * 64))
    with pytest.raises(LootPakError, match="sha256 mismatch"):
        _build.build(_config.parse_config(text), tmp_path / "o", FakeTools())
    assert not (tmp_path / "o").exists()


# ------------------------------------------------------------------------------------ write protection
def test_write_protection_refuses_the_base_folder_existing_out_folders_and_backups(tmp_path):
    paths = write_base(tmp_path)
    cfg = _config.parse_config(config_text(paths, "[enemydrops.Elite]\nguns_probability = 0.6\n"))
    before = {k: sha(v) for k, v in paths.items()}
    base_dir = tmp_path / "base"
    (tmp_path / "out7").mkdir()                                         # an existing outN (even empty)
    full = tmp_path / "somewhere"
    full.mkdir()
    (full / "keep.txt").write_text("x")
    backups = tmp_path / "backups" / "new"
    refused = [base_dir, base_dir / "sub", tmp_path, tmp_path / "out7", full, backups, base_dir / "t0.raw"]
    for target in refused:
        with pytest.raises(LootPakError):
            _build.build(cfg, target, FakeTools())
    assert {k: sha(v) for k, v in paths.items()} == before
    assert sorted(p.name for p in base_dir.iterdir()) == ["inv.ncs", "ref.pak", "t0.raw"]
    assert (full / "keep.txt").read_text() == "x" and not backups.exists()
    # a fresh sibling folder is fine, and an existing EMPTY non-outN folder may be reused
    empty = tmp_path / "empty_ok"
    empty.mkdir()
    assert _guard.check_out_dir(empty, list(paths.values())) == empty.resolve()
    assert _guard.check_out_dir(tmp_path / "fresh", list(paths.values()))


def test_extra_protected_dirs_from_config(tmp_path):
    paths = write_base(tmp_path)
    prot = tmp_path / "precious"
    prot.mkdir()
    with pytest.raises(LootPakError):
        _guard.check_out_dir(prot / "new", list(paths.values()), [prot])
    with pytest.raises(LootPakError, match="outside the output"):
        _guard.ensure_inside(tmp_path / "x", tmp_path / "y")


# ------------------------------------------------------------------------------------ subprocess adapter
def test_subprocess_adapter_builds_the_recipe_command_lines(monkeypatch, tmp_path):
    calls = []

    def fake_run(argv, capture_output, env, timeout):
        calls.append((argv, env.get("NCS_LEAFLOG")))
        return subprocess.CompletedProcess(argv, 0, stdout=b"out\r\n", stderr=b"err\r\n")

    monkeypatch.setattr(_tools.subprocess, "run", fake_run)
    t = _tools.SubprocessTools(Path("ncstool.exe"), Path("bl4.exe"), Path("uextract.exe"))
    assert t.leaves(Path("a.raw")) == "err\n" and calls[-1] == (["ncstool.exe", "leaves", "a.raw"], "1")
    t.strings(Path("a.raw"))
    assert calls[-1][0] == ["ncstool.exe", "strings", "a.raw"] and calls[-1][1] is None
    t.set_bits(Path("a.raw"), Path("b.raw"), 202900, [(237395, 13, 55, 313), (240640, 13, 63, 342)])
    assert calls[-1][0] == ["ncstool.exe", "set-bits", "a.raw", "b.raw", "202900",
                            "237395", "13", "55", "313", "240640", "13", "63", "342"]
    t.wrap(Path("b.raw"), Path("b.ncs"))
    assert calls[-1][0] == ["ncstool.exe", "wrap", "b.raw", "b.ncs"]
    t.decode(Path("b.ncs"))
    assert calls[-1][0] == ["bl4.exe", "ncs", "show", "b.ncs"]
    t.mkpak(Path("o.pak"), "../../../", 2190688979, Path("ref.pak"), [("N/a.ncs", Path("a")), ("N/b.ncs", Path("b"))])
    assert calls[-1][0] == ["ncstool.exe", "mkpak", "o.pak", "../../../", "2190688979", "ref.pak", "N/a.ncs=a", "N/b.ncs=b"]
    t.mkpak(Path("o.pak"), "m", None, Path("ref.pak"), [])
    assert calls[-1][0][4] == "none"
    t.extract(tmp_path, tmp_path / "ex")
    assert calls[-1][0] == ["uextract.exe", "pak", str(tmp_path), "-o", str(tmp_path / "ex")]


def test_subprocess_adapter_reports_failures_and_missing_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(_tools.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 3, stdout=b"", stderr=b"boom"))
    t = _tools.SubprocessTools(Path("n"), Path("b"), Path("u"))
    with pytest.raises(LootPakError, match="failed.*boom"):
        t.wrap(Path("a"), Path("b"))
    with pytest.raises(LootPakError, match="missing"):
        _tools.SubprocessTools.from_settings({"ncstool": "x"})
    with pytest.raises(LootPakError, match="tool not found"):
        _tools.SubprocessTools.from_settings({"ncstool": str(tmp_path / "n"), "bl4": str(tmp_path / "b"),
                                              "uextract": str(tmp_path / "u")})


# ------------------------------------------------------------------------------------ cell + CLI wiring
def make_forge(tmp_path, tools):
    cfg = Config.default(root=tmp_path)
    cell = LootPakModule(ModuleContext("lootpak", cfg, {}), tools=tools)
    return Forge.build(cfg, overrides={"lootpak": cell}, only=["lootpak"]), cell


def test_cell_is_registered_healthy_and_conforms_to_its_port():
    forge = Forge.build(Config.default(root=ROOT), only=["lootpak"])
    assert forge.summary() == {"lootpak": "ok"}
    cell = forge.lootpak
    assert conformance_problems(cell, LootPakPort) == [] and LootPakModule.requires == ()
    assert cell.health().ok and "self-checks passed" in cell.health().summary


def test_cell_plan_and_build_through_the_port(tmp_path):
    paths = write_base(tmp_path)
    cfg_file = tmp_path / "c.toml"
    cfg_file.write_text(config_text(paths, BODY), encoding="utf-8")
    forge, cell = make_forge(tmp_path, FakeTools())
    cfg = cell.load_config(str(cfg_file))
    assert len(cell.plan(cfg).changes) == 3
    res = cell.build(cfg, str(tmp_path / "o"))
    assert res.pak_path.is_file()
    with pytest.raises(ConfigError, match="no such"):
        cell.load_config(str(tmp_path / "missing.toml"))


def test_cli_lootpak_plan_and_build(tmp_path, capsys):
    from bl4forge.cli import main
    paths = write_base(tmp_path)
    cfg_file = tmp_path / "c.toml"
    cfg_file.write_text(config_text(paths, BODY), encoding="utf-8")
    forge, _ = make_forge(tmp_path, FakeTools())
    assert main(["lootpak-plan", str(cfg_file)], forge=forge) == 0
    out = capsys.readouterr().out
    assert "plan t: 3 set_leaf" in out and not (tmp_path / "o").exists()
    assert main(["lootpak-build", str(cfg_file), str(tmp_path / "o")], forge=forge) == 0
    out = capsys.readouterr().out
    assert "gate passed" in out and "sha256" in out and (tmp_path / "o" / "manifest.json").is_file()
    # refusing is a user error (exit 2), not a crash
    assert main(["lootpak-build", str(cfg_file), str(tmp_path / "base")], forge=forge) == 2
    assert "refusing" in capsys.readouterr().err


def test_config_toml_lootpak_table_is_read(tmp_path):
    (tmp_path / "config.toml").write_text('[lootpak]\nncstool = "n"\nmodwork = "m"\n', encoding="utf-8")
    assert Config.load(root=tmp_path).lootpak == {"ncstool": "n", "modwork": "m"}
    (tmp_path / "config.toml").write_text('[lootpak]\nncstool = 3\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        Config.load(root=tmp_path)


def test_no_save_key_or_console_code_in_the_cell():
    src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src" / "bl4forge" / "modules" / "lootpak").glob("*.py"))
    for banned in ("ps5_key", "pc_base_key", "socket", "urllib", "requests", "ftp", "http"):
        assert banned not in src.lower(), banned


def test_real_raw_locates_every_oneplayer_constant_of_the_spawn_balance_table():
    tools, modwork = _real_tools()
    raw = modwork / "out14" / "work" / "t0_v11.raw"
    dec = modwork / "out14" / "decoded_t0_v11.txt"
    if not raw.is_file() or not dec.is_file():
        pytest.skip("out14 raw/decode absent")
    base_decode = dec.read_text(encoding="utf-8")
    table = _decode.find_table(_decode.parse_decode(base_decode), "table_playercountspawnbalancedata")
    rows = [r.name for r in table.rows]
    assert rows[0] == "Default" and len(rows) == 6
    import tempfile
    with tempfile.TemporaryDirectory(prefix="lootpak-test-") as td:
        located, log, pool = _locate.locate(tools, Path(td), raw, base_decode, {table.key: rows})
    for r in rows:
        loc = located[(table.key, r, "oneplayer.constant")]
        assert loc.consistent and loc.dleaf.path == "oneplayer.constant"
    # all four maps of a row are told apart: distinct leaves for the four constants
    for r in rows:
        pos = {located[(table.key, r, m + ".constant")].leaf.bitpos for m in ("oneplayer", "twoplayers", "threeplayers", "fourplayers")}
        assert len(pos) == 4


# ------------------------------------------------------------------------------------ GOLDEN (real files)
def _real_tools():
    cfg = Config.load(root=ROOT)
    s = cfg.lootpak
    need = [s.get(k) for k in ("ncstool", "bl4", "uextract", "modwork")]
    if not all(need) or not all(Path(p).exists() for p in need):
        pytest.skip("[lootpak] tools/modwork not configured or absent in config.toml")
    return _tools.SubprocessTools.from_settings(s), Path(s["modwork"])


@pytest.mark.parametrize("example, needs, golden_sha", [
    ("out13.toml", "out10/work/t0_v7.raw", "0c9142bac9dd78cb9e8ab539729351d22d28564971510d5ede6a141ab301cda4"),
    ("out14.toml", "out13/work/t0_v10.raw", "23364fa4fcd616be025224de645494a2caa11d1a7e5f82baea7abff83ee5fb5d"),
    ("out16.toml", "out14/work/t0_v11.raw", "82adbfed8321fd89ef35a60e9dd0bc2d16c854994c60103809604b6c64f25107"),
])
def test_golden_reproduces_the_recorded_pak(tmp_path, example, needs, golden_sha):
    tools, modwork = _real_tools()
    if not (modwork / needs).is_file() or not (modwork / "out3" / "pakchunk100-ps5_P.pak").is_file():
        pytest.skip("modwork input files absent: %s" % needs)
    cfg = _config.load_config_file(EXAMPLES / example, modwork)
    before = {k: sha(p) for k, p in (("raw", cfg.base.raw), ("inv", cfg.base.inventory), ("ref", cfg.base.reference_pak))}
    res = _build.build(cfg, tmp_path / "golden", tools)
    assert res.pak_sha256 == golden_sha
    assert res.pak_bytes == 290324
    assert len(res.diff) == len(res.plan.changes)
    man = json.loads(res.manifest_path.read_text(encoding="utf-8"))
    assert man["outputs"]["pak"]["sha256"] == golden_sha and man["tools"]["ncstool"]
    assert before == {k: sha(p) for k, p in (("raw", cfg.base.raw), ("inv", cfg.base.inventory),
                                              ("ref", cfg.base.reference_pak))}
