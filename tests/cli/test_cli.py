"""Tests for the command line (outer layer). Real modules everywhere except `build`, which uses a
tiny fake builder (the real builder has its own tests; `test_build_with_real_builder` runs the
README example loadouts end to end and skips until the builder is healthy)."""
from __future__ import annotations

import html as htmllib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bl4forge.cli import main
from bl4forge.core.config import Config
from bl4forge.core.doctor import diagnose, ok as doctor_ok
from bl4forge.core.forge import Forge
from bl4forge.core.module import Module
from bl4forge.core.ports import OpsPort
from bl4forge.core.types import CatalogEntry, Loadout, LoadoutItem, SearchQuery
from tests.dataset import D

ROOT = Path(__file__).resolve().parents[2]
BL4_FORGE_ENV_KEYS = ("BL4FORGE_CONFIG",)


# ---- helpers -----------------------------------------------------------------------------------

def run(capsys, argv, forge=None):
    """Run main() and return (exit code, stdout, stderr)."""
    capsys.readouterr()
    code = main(list(argv), forge=forge)
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def jrun(capsys, argv, forge=None):
    code, out, err = run(capsys, argv, forge)
    assert code == 0, err
    return json.loads(out)


def assert_clean_failure(code, out, err, expect_code=2, needle=None):
    """An expected failure: right exit code, one human line on stderr, no traceback."""
    assert code == expect_code, (code, out, err)
    assert "Traceback" not in err and "Traceback" not in out
    assert err.startswith("error: ") or "usage:" in err, err
    if needle:
        assert needle in err, err


def write_cfg(tmp_path, text, name="config.toml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def _no_ambient_config(monkeypatch):
    for key in BL4_FORGE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(scope="session")
def serials(forge):
    """A few real serials at their stored level 50."""
    cat, codec = forge.catalog, forge.codec
    shotgun = cat.search(SearchQuery(query=D.SHOTGUN_Q, element="cryo", type="shotgun", limit=1)).entries[0].serial
    shield = cat.search(SearchQuery(type="shield", limit=1)).entries[0].serial
    classmod = cat.search(SearchQuery(type="classmod", character="gravitar", limit=1)).entries[0].serial
    by_cat = {}
    for e in cat.search(SearchQuery(type="shotgun", limit=400)).entries:
        by_cat.setdefault(codec.get_category_id(codec.decode(e.serial)), []).append(e.serial)
    a, b = next(v[:2] for v in by_cat.values() if len(v) >= 2)
    return {"shotgun": shotgun, "shield": shield, "classmod": classmod, "pair": (a, b)}


@pytest.fixture(scope="session")
def cfg_nopack3(tmp_path_factory):
    return write_cfg(tmp_path_factory.mktemp("cfg"),
                     '[ownership]\npacks = ["coregame","bounty_pack_1","bounty_pack_2","bounty_pack_4","bounty_pack_5"]\n')


@pytest.fixture(scope="session")
def forge_nopack3(cfg_nopack3):
    return Forge.build(Config.load(path=cfg_nopack3))


# ---- import hygiene / top level -----------------------------------------------------------------

def test_import_is_side_effect_free():
    code = "import bl4forge.cli as c; assert callable(c.main)"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONPATH=str(ROOT / "src")), cwd=str(ROOT))
    assert r.returncode == 0, r.stderr
    assert r.stdout == "" and r.stderr == ""


def test_python_dash_m_runs_and_exits_cleanly(serials):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    r = subprocess.run([sys.executable, "-m", "bl4forge", "decode", "--serial", serials["shotgun"]],
                       capture_output=True, text=True, env=env, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr
    assert "level: 50" in r.stdout
    r = subprocess.run([sys.executable, "-m", "bl4forge", "decode", "--serial", "garbage"],
                       capture_output=True, text=True, env=env, cwd=str(ROOT))
    assert r.returncode == 2 and "Traceback" not in r.stderr and r.stderr.startswith("error: ")


def test_no_command_is_a_usage_error(capsys):
    code, out, err = run(capsys, [])
    assert code == 2 and "usage:" in err


def test_help_and_version(capsys, forge):
    code, out, err = run(capsys, ["--help"], forge)
    assert code == 0 and "exit codes:" in out and "doctor" in out
    code, out, err = run(capsys, ["search", "--help"], forge)
    assert code == 0 and "--include-unowned" in out and "--no-verify" in out
    code, out, err = run(capsys, ["--version"], forge)
    assert code == 0 and out.startswith("bl4forge ")


# ---- catalog ------------------------------------------------------------------------------------

def test_catalog_text(capsys, forge):
    code, out, err = run(capsys, ["catalog"], forge)
    assert code == 0 and err == ""
    assert "Total codes: %d" % forge.catalog.count() in out
    for title in ("By type:", "By weapon type:", "By rarity:", "By manufacturer:"):
        assert title in out
    top_type, top_n = next(iter(forge.catalog.stats()["by_type"].items()))
    assert any(l.split() == [top_type, str(top_n)] for l in out.splitlines())


def test_catalog_json(capsys, forge):
    data = jrun(capsys, ["catalog", "--json"], forge)
    stats = forge.catalog.stats()
    assert data["total"] == forge.catalog.count()
    for key in stats:
        assert data[key] == dict(stats[key])


# ---- search -------------------------------------------------------------------------------------

SEARCH_CASES = [
    (["--query", D.SHOTGUN_Q, "--element", "cryo", "--type", "shotgun", "--limit", "3"],
     dict(query=D.SHOTGUN_Q, element="cryo", type="shotgun", limit=3)),
    (["--type", "ar", "--limit", "5"], dict(type="ar", limit=5)),
    (["--type", "sg", "--element", "electric", "--limit", "5"], dict(type="sg", element="electric", limit=5)),
    (["--manufacturer", D.MFR, "--rarity", "legendary", "--limit", "4"],
     dict(manufacturer=D.MFR, rarity="legendary", limit=4)),
    (["--type", "classmod", "--character", "paladin", "--limit", "3"],
     dict(type="classmod", character="paladin", limit=3)),
    (["--type", "repkit", "--limit", "3"], dict(type="repkit", limit=3)),
    (["--query", D.WOMBO_Q, "--limit", "2"], dict(query=D.WOMBO_Q, limit=2)),
    (["--type", "pistol", "--element", "fire", "--no-verify", "--limit", "6"],
     dict(type="pistol", element="fire", limit=6, verify_element=False)),
]


@pytest.mark.parametrize("argv,query", SEARCH_CASES)
def test_search_json_equals_catalog_search(capsys, forge, argv, query):
    expected = forge.catalog.search(SearchQuery(**query))
    assert expected.entries, "test case should find something"
    data = jrun(capsys, ["search"] + argv + ["--no-relevel", "--json"], forge)
    assert [r["serial"] for r in data["results"]] == [e.serial for e in expected.entries]
    assert [r["name"] for r in data["results"]] == [e.name for e in expected.entries]
    assert [r["element"] for r in data["results"]] == [e.element for e in expected.entries]
    assert data["count"] == len(expected.entries) and data["level"] is None
    assert data["dropped_element_mismatch"] == expected.dropped_element_mismatch
    assert data["hidden"] == []


def test_search_relevels_to_config_level_by_default(capsys, forge):
    q = SearchQuery(query=D.SHOTGUN_Q, element="cryo", type="shotgun", limit=3)
    expected = forge.catalog.search(q)
    data = jrun(capsys, ["search", "--query", D.SHOTGUN_Q, "--element", "cryo", "--type", "shotgun",
                         "--limit", "3", "--json"], forge)
    assert data["level"] == forge.config.level == 60
    assert [r["serial"] for r in data["results"]] == [forge.codec.relevel(e.serial, 60) for e in expected.entries]
    assert all(r["level"] == 60 and r["warnings"] == [] for r in data["results"])
    data = jrun(capsys, ["search", "--query", D.SHOTGUN_Q, "--type", "shotgun", "--limit", "1",
                         "--level", "42", "--json"], forge)
    assert data["results"][0]["level"] == 42


def test_search_text_format(capsys, forge):
    code, out, err = run(capsys, ["search", "--query", D.SHOTGUN_Q, "--element", "cryo", "--type", "shotgun",
                                  "--level", "60", "--limit", "3"], forge)
    assert code == 0 and err == ""
    expected = forge.catalog.search(SearchQuery(query=D.SHOTGUN_Q, element="cryo", type="shotgun", limit=3))
    lines = [l for l in out.splitlines() if l.strip()]
    assert len(lines) == len(expected.entries)
    for i, (line, e) in enumerate(zip(lines, expected.entries), 1):
        assert line.startswith("%2d. " % i)
        assert e.name[:34] in line and "Cryo" in line and "Lv60" in line
        assert forge.codec.relevel(e.serial, 60) in line


def test_search_classmod_defaults_to_configured_character(capsys, forge):
    expected = forge.catalog.search(SearchQuery(type="classmod", character="gravitar", limit=5))
    code, out, err = run(capsys, ["search", "--type", "classmod", "--limit", "5", "--no-relevel", "--json"], forge)
    assert code == 0 and "gravitar" in err
    assert [r["serial"] for r in json.loads(out)["results"]] == [e.serial for e in expected.entries]
    # an explicit character wins and needs no note
    code, out, err = run(capsys, ["search", "--type", "class_mod", "--character", "paladin",
                                  "--limit", "5", "--no-relevel", "--json"], forge)
    paladin = forge.catalog.search(SearchQuery(type="class_mod", character="paladin", limit=5))
    assert code == 0 and err == ""
    assert [r["serial"] for r in json.loads(out)["results"]] == [e.serial for e in paladin.entries]
    # the default must NOT leak into other types (it would filter everything out)
    data = jrun(capsys, ["search", "--type", "shotgun", "--limit", "3", "--no-relevel", "--json"], forge)
    assert data["count"] == 3


def test_search_no_match_is_not_an_error(capsys, forge):
    code, out, err = run(capsys, ["search", "--query", "zzznotanitem"], forge)
    assert (code, out.strip(), err) == (0, "No matches.", "")
    assert jrun(capsys, ["search", "--query", "zzznotanitem", "--json"], forge)["results"] == []


def test_search_no_verify_notes_that_labels_are_unchecked(capsys, forge):
    code, out, err = run(capsys, ["search", "--type", "pistol", "--element", "fire", "--no-verify", "--limit", "2"], forge)
    assert code == 0 and "--no-verify" in err


def test_search_reports_dropped_element_labels(capsys, forge):
    """Find a query where verification drops rows and check the cli says so."""
    found = None
    for el in ("cryo", "fire", "shock", "radiation", "corrosive", "impact"):
        for typ in ("pistol", "shotgun", "smg", "ar", "sniper", "heavy"):
            res = forge.catalog.search(SearchQuery(type=typ, element=el, limit=100000))
            if res.dropped_element_mismatch:
                found = (typ, el, res)
                break
        if found:
            break
    if not found:
        pytest.skip("this database has no mislabelled weapons to report")
    typ, el, res = found
    code, out, err = run(capsys, ["search", "--type", typ, "--element", el, "--limit", "100000", "--no-relevel"], forge)
    assert code == 0
    assert "%d dropped: database element label disagreed with the serial" % res.dropped_element_mismatch in out
    data = jrun(capsys, ["search", "--type", typ, "--element", el, "--limit", "100000", "--no-relevel", "--json"], forge)
    assert data["dropped_element_mismatch"] == res.dropped_element_mismatch


def test_search_hidden_by_pack_and_include_unowned(capsys, cfg_nopack3, forge_nopack3):
    hidden = forge_nopack3.catalog.search(SearchQuery(query="frangible", limit=100000)).hidden_by_pack
    assert hidden == {"bounty_pack_3": 26}
    label = forge_nopack3.rules.pack_label("bounty_pack_3")
    assert label and label != "bounty_pack_3"

    # through --config, exactly as a user would run it
    code, out, err = run(capsys, ["--config", str(cfg_nopack3), "search", "--query", "frangible",
                                  "--limit", "100000", "--no-relevel"])
    assert code == 0
    assert "26 hidden: needs %s" % label in out
    assert "--include-unowned" in out

    data = jrun(capsys, ["search", "--query", "frangible", "--limit", "100000", "--no-relevel", "--json"], forge_nopack3)
    assert data["hidden"] == [{"pack": "bounty_pack_3", "label": label, "count": 26}]

    shown = jrun(capsys, ["search", "--query", "frangible", "--limit", "100000", "--no-relevel",
                          "--include-unowned", "--json"], forge_nopack3)
    assert shown["hidden"] == []
    assert shown["count"] == data["count"] + 26
    code, out, err = run(capsys, ["search", "--query", "frangible", "--limit", "100000", "--no-relevel",
                                  "--include-unowned"], forge_nopack3)
    assert "hidden" not in out


@pytest.mark.parametrize("argv", [
    ["search", "--limit", "0"], ["search", "--limit", "many"],
    ["search", "--level", "0"], ["search", "--level", "101"], ["search", "--level", "x"],
])
def test_search_bad_numbers_are_usage_errors(capsys, forge, argv):
    code, out, err = run(capsys, argv, forge)
    assert code == 2 and "usage:" in err and "Traceback" not in err and out == ""


def test_search_unknown_element_is_a_clean_error(capsys, forge):
    code, out, err = run(capsys, ["search", "--element", "plasma"], forge)
    assert_clean_failure(code, out, err, needle="unknown element 'plasma'")
    assert out == ""


# ---- decode / relevel ---------------------------------------------------------------------------

def test_decode(capsys, forge, serials):
    s = serials["shotgun"]
    blocks = forge.codec.decode(s)
    code, out, err = run(capsys, ["decode", "--serial", s], forge)
    assert code == 0 and err == ""
    assert out.splitlines() == ["parts: %s" % forge.codec.parts_string(blocks),
                                "level: %s" % forge.codec.get_level(blocks),
                                "category index: %s" % forge.codec.get_category_id(blocks)]
    data = jrun(capsys, ["decode", "--serial", s, "--json"], forge)
    assert data == {"parts": forge.codec.parts_string(blocks), "level": 50,
                    "category_id": forge.codec.get_category_id(blocks)}


def test_relevel_equals_codec(capsys, forge, serials):
    s = serials["shotgun"]
    code, out, err = run(capsys, ["relevel", "--serial", s, "--level", "60"], forge)
    assert code == 0 and err == "" and out.strip() == forge.codec.relevel(s, 60)
    code, out, err = run(capsys, ["relevel", "--serial", s, "--level", "33"], forge)
    assert out.strip() == forge.codec.relevel(s, 33)
    code, out, err = run(capsys, ["relevel", "--serial", s], forge)       # config default level
    assert out.strip() == forge.codec.relevel(s, forge.config.level)


def test_relevel_default_level_comes_from_config(capsys, tmp_path, forge, serials):
    cfg = write_cfg(tmp_path, "[forge]\nlevel = 55\n")
    s = serials["shotgun"]
    code, out, err = run(capsys, ["--config", str(cfg), "relevel", "--serial", s])
    assert code == 0 and out.strip() == forge.codec.relevel(s, 55)
    # the flag is accepted after the command too
    code, out, err = run(capsys, ["relevel", "--serial", s, "--config", str(cfg)])
    assert code == 0 and out.strip() == forge.codec.relevel(s, 55)
    # and so is the environment variable
    code, out, err = run_with_env(capsys, {"BL4FORGE_CONFIG": str(cfg)}, ["relevel", "--serial", s])
    assert code == 0 and out.strip() == forge.codec.relevel(s, 55)
    # search follows the config level as well
    data = jrun(capsys, ["--config", str(cfg), "search", "--query", D.SHOTGUN_Q, "--limit", "1", "--json"])
    assert data["level"] == 55 and data["results"][0]["level"] == 55


def run_with_env(capsys, env, argv):
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        return run(capsys, argv)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_bad_config_is_a_clean_error(capsys, tmp_path):
    code, out, err = run(capsys, ["--config", str(tmp_path / "missing.toml"), "catalog"])
    assert_clean_failure(code, out, err, needle="no such config file")
    code, out, err = run_with_env(capsys, {"BL4FORGE_CONFIG": str(tmp_path / "gone.toml")}, ["catalog"])
    assert_clean_failure(code, out, err, needle="BL4FORGE_CONFIG")
    bad = write_cfg(tmp_path, "this is = = not toml", "bad.toml")
    code, out, err = run(capsys, ["--config", str(bad), "catalog"])
    assert_clean_failure(code, out, err, needle="config error")
    lvl = write_cfg(tmp_path, "[forge]\nlevel = 500\n", "lvl.toml")
    code, out, err = run(capsys, ["--config", str(lvl), "catalog"])
    assert_clean_failure(code, out, err, needle="forge.level")


# ---- identify -----------------------------------------------------------------------------------

def test_identify_text(capsys, forge, serials):
    s = serials["shotgun"]
    info = forge.ops.describe(s)
    code, out, err = run(capsys, ["identify", "--serial", s], forge)
    assert code == 0 and err == ""
    assert "Item:" in out and info.display_name in out
    assert "%s (category %s)" % (info.category, info.category_id) in out
    assert "Level:         %s" % info.level in out and "Rarity:        %s" % info.rarity in out
    assert "Element:       Cryo" in out
    assert "Content:       Base game" in out and "NOT OWNED" not in out
    assert "Drop odds:" in out and forge.ops.format_odds(forge.ops.rarity_estimate(info)) in out
    assert "Parts (position: name):" in out
    for i, part in enumerate(info.parts):
        assert "%2d: %s" % (i, part.label()) in out


def test_identify_json_equals_describe(capsys, forge, serials):
    for key in ("shotgun", "shield", "classmod"):
        s = serials[key]
        data = jrun(capsys, ["identify", "--serial", s, "--json"], forge)
        assert data == json.loads(json.dumps(forge.ops.describe(s).to_dict()))
    s = serials["shotgun"]
    data = jrun(capsys, ["identify", "--serial", s, "--json", "--odds"], forge)
    info = forge.ops.describe(s)
    assert data.pop("odds") == json.loads(json.dumps(forge.ops.rarity_estimate(info)))
    assert data == json.loads(json.dumps(info.to_dict()))


def test_identify_gear_has_no_element(capsys, forge, serials):
    code, out, err = run(capsys, ["identify", "--serial", serials["shield"]], forge)
    assert code == 0 and "Element:       -" in out


def test_identify_reports_unowned_content(capsys, forge_nopack3):
    entries = forge_nopack3.catalog.search(SearchQuery(query="frangible", limit=100000, include_unowned=True)).entries
    s = next(e.serial for e in entries if not forge_nopack3.rules.serial_ownership(e.serial)[0])
    code, out, err = run(capsys, ["identify", "--serial", s], forge_nopack3)
    assert code == 0 and "[NOT OWNED]" in out
    assert forge_nopack3.rules.pack_label("bounty_pack_3") in out


# ---- set-element / reseed -----------------------------------------------------------------------

def test_set_element(capsys, forge, serials):
    s = serials["shotgun"]                       # cryo
    code, out, err = run(capsys, ["set-element", "--serial", s, "--element", "fire"], forge)
    new = forge.ops.set_element(s, "fire")
    assert code == 0 and out.strip() == new
    assert forge.ops.describe(new).element == "fire"
    assert "-> " in err and "Fire" in err
    # alias spelling + re-level in one go
    code, out, err = run(capsys, ["set-element", "--serial", s, "--element", "electric", "--level", "60"], forge)
    assert out.strip() == forge.codec.relevel(forge.ops.set_element(s, "electric"), 60)
    assert forge.ops.describe(out.strip()).element == "shock"
    # impact strips the element part
    code, out, err = run(capsys, ["set-element", "--serial", s, "--element", "impact"], forge)
    assert out.strip() == forge.ops.set_element(s, "impact")
    assert forge.ops.describe(out.strip()).element == "impact"
    # setting the element it already has changes nothing, and says so
    code, out, err = run(capsys, ["set-element", "--serial", s, "--element", "cryo"], forge)
    assert out.strip() == s and "serial unchanged" in err


def test_set_element_refusals(capsys, forge, serials):
    code, out, err = run(capsys, ["set-element", "--serial", serials["shotgun"], "--element", "plasma"], forge)
    assert_clean_failure(code, out, err, needle="unknown element")
    assert out == ""
    code, out, err = run(capsys, ["set-element", "--serial", serials["shield"], "--element", "cryo"], forge)
    assert_clean_failure(code, out, err, needle="gear")
    assert out == ""
    code, out, err = run(capsys, ["set-element", "--serial", "garbage", "--element", "cryo"], forge)
    assert_clean_failure(code, out, err, needle="not a Borderlands 4 item serial")


def test_reseed(capsys, forge, serials):
    s = serials["shotgun"]
    code, out, err = run(capsys, ["reseed", "--serial", s, "--seed", "1234"], forge)
    assert code == 0 and out.strip() == forge.ops.set_seed(s, 1234)
    assert forge.ops.get_seed(out.strip()) == 1234
    assert "seed 1234 (was %s)" % forge.ops.get_seed(s) in err


@pytest.mark.parametrize("seed", ["-3", "2147483648"])
def test_reseed_rejects_out_of_range_seeds(capsys, forge, serials, seed):
    code, out, err = run(capsys, ["reseed", "--serial", serials["shotgun"], "--seed", seed], forge)
    assert_clean_failure(code, out, err)
    assert out == ""


# ---- diff / swap / validate -----------------------------------------------------------------------

def test_diff(capsys, forge, serials):
    s = serials["shotgun"]
    code, out, err = run(capsys, ["diff", "--a", s, "--b", s], forge)
    assert (code, out.strip()) == (0, "Identical.")
    s60 = forge.codec.relevel(s, 60)
    code, out, err = run(capsys, ["diff", "--a", s, "--b", s60], forge)
    assert code == 0 and out.splitlines()[0].split() == ["FIELD", "A", "B"]
    assert out.splitlines()[1].split() == ["level", "50", "60"]
    data = jrun(capsys, ["diff", "--a", s, "--b", s60, "--json"], forge)
    assert data == {"identical": False, "differences": forge.ops.diff(s, s60)}
    assert jrun(capsys, ["diff", "--a", s, "--b", s, "--json"], forge) == {"identical": True, "differences": []}


def test_swap_same_category(capsys, forge, serials):
    base, source = serials["pair"]
    code, out, err = run(capsys, ["swap", "--base", base, "--source", source, "--positions", "1, 2"], forge)
    assert code == 0
    assert out.strip() == forge.ops.swap_parts(base, source, [1, 2])
    assert err.startswith("-> ") and "structural checks only" in err


def test_swap_refuses_cross_category(capsys, forge, serials):
    code, out, err = run(capsys, ["swap", "--base", serials["shotgun"], "--source", serials["shield"],
                                  "--positions", "1"], forge)
    assert_clean_failure(code, out, err, needle="swap refused")
    assert "different item categories" in err and out == ""
    assert len(err.strip().splitlines()) == 1
    # explicitly allowed: works, and the structural problems it causes are reported as warnings
    code, out, err = run(capsys, ["swap", "--base", serials["shotgun"], "--source", serials["shield"],
                                  "--positions", "0", "--allow-cross"], forge)
    new = forge.ops.swap_parts(serials["shotgun"], serials["shield"], [0], allow_cross=True)
    assert code == 0 and out.strip() == new
    for problem in forge.rules.validate(new):
        assert "warning: %s" % problem in err


@pytest.mark.parametrize("positions", ["a,b", ",", "", "999", "-1"])
def test_swap_bad_positions(capsys, forge, serials, positions):
    base, source = serials["pair"]
    code, out, err = run(capsys, ["swap", "--base", base, "--source", source, "--positions", positions], forge)
    assert_clean_failure(code, out, err)
    assert out == ""


def test_validate(capsys, forge, serials):
    s = serials["shotgun"]
    code, out, err = run(capsys, ["validate", "--serial", s], forge)
    assert code == 0 and out.startswith("OK") and "not a guarantee" in out
    assert jrun(capsys, ["validate", "--serial", s, "--json"], forge) == {"serial": s, "ok": True, "problems": []}


def test_validate_reports_problems_with_exit_1(capsys, forge, serials):
    bad = forge.ops.swap_parts(serials["shotgun"], serials["shield"], [0], allow_cross=True)
    problems = forge.rules.validate(bad)
    assert problems, "the cross swap should leave a structural problem"
    code, out, err = run(capsys, ["validate", "--serial", bad], forge)
    assert code == 1 and err == ""
    assert out.splitlines() == ["problem: %s" % p for p in problems]
    code, out, err = run(capsys, ["validate", "--serial", bad, "--json"], forge)
    assert code == 1 and json.loads(out) == {"serial": bad, "ok": False, "problems": problems}


# ---- bad input never produces a traceback ---------------------------------------------------------

GARBAGE_CASES = [
    ["decode", "--serial", "garbage"],
    ["relevel", "--serial", "garbage", "--level", "60"],
    ["identify", "--serial", "garbage"],
    ["identify", "--serial", "garbage", "--json"],
    ["set-element", "--serial", "garbage", "--element", "cryo"],
    ["reseed", "--serial", "garbage", "--seed", "5"],
    ["diff", "--a", "garbage", "--b", "garbage"],
    ["swap", "--base", "garbage", "--source", "garbage", "--positions", "1"],
    ["validate", "--serial", "garbage"],
    ["identify", "--serial", "@Unotreallyaserial"],
    ["decode", "--serial", ""],
]


@pytest.mark.parametrize("argv", GARBAGE_CASES)
def test_garbage_serial_is_a_clean_error(capsys, forge, argv):
    code, out, err = run(capsys, argv, forge)
    assert_clean_failure(code, out, err)
    assert out == ""
    assert len(err.strip().splitlines()) == 1


def test_debug_flag_shows_the_traceback(capsys, forge):
    code, out, err = run(capsys, ["decode", "--serial", "garbage", "--debug"], forge)
    assert code == 2 and "Traceback" in err and err.startswith("error: ")
    code, out, err = run(capsys, ["--debug", "decode", "--serial", "garbage"], forge)
    assert code == 2 and "Traceback" in err


# ---- module availability --------------------------------------------------------------------------

class BoomOps(Module):
    name = "ops"
    purpose = "always fails to start"
    requires = ("codec", "data", "rules")
    port = OpsPort

    def __init__(self, ctx):
        raise RuntimeError("boom")


@pytest.fixture()
def sick_forge(config):
    forge = Forge.build(config, overrides={"ops": BoomOps})
    assert forge.states["ops"].state == "failed"
    assert forge.states["catalog"].state == "blocked"
    return forge


def test_unavailable_module_is_named_with_a_doctor_hint(capsys, sick_forge, serials):
    code, out, err = run(capsys, ["identify", "--serial", serials["shotgun"]], sick_forge)
    assert_clean_failure(code, out, err, expect_code=4, needle="module 'ops'")
    assert "boom" in err and "bl4forge doctor" in err
    assert len(err.strip().splitlines()) == 1 and out == ""


def test_blocked_module_names_what_it_is_waiting_for(capsys, sick_forge):
    code, out, err = run(capsys, ["search", "--query", "anarchy"], sick_forge)
    assert_clean_failure(code, out, err, expect_code=4, needle="module 'catalog'")
    assert "ops" in err and "bl4forge doctor" in err
    for argv in (["catalog"], ["set-element", "--serial", "x", "--element", "cryo"], ["diff", "--a", "x", "--b", "y"]):
        code, out, err = run(capsys, argv, sick_forge)
        assert code == 4 and "bl4forge doctor" in err and "Traceback" not in err


def test_a_sick_module_does_not_stop_unrelated_commands(capsys, sick_forge, serials):
    code, out, err = run(capsys, ["decode", "--serial", serials["shotgun"]], sick_forge)
    assert code == 0 and "level: 50" in out and err == ""
    code, out, err = run(capsys, ["relevel", "--serial", serials["shotgun"], "--level", "60"], sick_forge)
    assert code == 0
    code, out, err = run(capsys, ["validate", "--serial", serials["shotgun"]], sick_forge)
    assert code == 0                                     # rules needs only codec and data


def test_doctor_shows_the_sick_module(capsys, sick_forge):
    code, out, err = run(capsys, ["doctor"], sick_forge)
    assert code == 1 and "FAILED" in out and "boom" in out
    assert "BLOCKED" in out


def test_degraded_module_still_works_with_a_one_line_warning(capsys, config, serials):
    forge = Forge.build(config, only=["codec"])
    forge.states["codec"].state = "degraded"
    forge.states["codec"].detail = "known-answer check failed"
    code, out, err = run(capsys, ["decode", "--serial", serials["shotgun"]], forge)
    assert code == 0 and "level: 50" in out
    assert err.strip().splitlines() == [
        "warning: module 'codec' is degraded (known-answer check failed); results may be incomplete - "
        "run 'bl4forge doctor' for details"]


# ---- doctor ----------------------------------------------------------------------------------------

def test_doctor(capsys, forge):
    healthy = doctor_ok(diagnose(forge))
    code, out, err = run(capsys, ["doctor"], forge)
    assert code == (0 if healthy else 1) and err == ""
    assert "modules healthy" in out
    for name in forge.states:
        assert name in out
    code, out, err = run(capsys, ["doctor", "-v"], forge)
    assert "purpose:" in out
    rows = jrun_any(capsys, ["doctor", "--json"], forge)
    assert {r["name"] for r in rows} == set(forge.states)


def jrun_any(capsys, argv, forge):
    code, out, err = run(capsys, argv, forge)
    assert code in (0, 1), err
    return json.loads(out)


# ---- stdout is parseable JSON for every --json -------------------------------------------------------

@pytest.mark.parametrize("argv", [
    ["catalog", "--json"],
    ["search", "--query", D.SHOTGUN_Q, "--limit", "2", "--json"],
    ["search", "--query", "zzznotanitem", "--json"],
    ["decode", "--serial", "{shotgun}", "--json"],
    ["identify", "--serial", "{shotgun}", "--json"],
    ["identify", "--serial", "{shield}", "--json", "--odds"],
    ["diff", "--a", "{shotgun}", "--b", "{shield}", "--json"],
    ["validate", "--serial", "{shotgun}", "--json"],
    ["doctor", "--json"],
])
def test_json_flags_print_only_json_on_stdout(capsys, forge, serials, argv):
    argv = [a.format(**serials) if "{" in a else a for a in argv]
    code, out, err = run(capsys, argv, forge)
    assert code in (0, 1), err
    json.loads(out)                       # the whole of stdout, nothing else


# ---- build (fake builder) ----------------------------------------------------------------------------

class FakeBuilder:
    """A stand-in BuilderPort: resolves requests with the real catalog/codec/ops, records the calls."""
    name = "builder"

    def __init__(self, forge, loadout_warnings=(), item_warnings=(), error=None):
        self.f = forge
        self.calls = []
        self.loadout_warnings = tuple(loadout_warnings)
        self.item_warnings = tuple(item_warnings)
        self.error = error

    def enrich(self, entry, level=None):
        raise NotImplementedError

    def build(self, requests, level=None, title="Break Free Loadout"):
        self.calls.append({"requests": list(requests), "level": level, "title": title})
        if self.error:
            raise self.error
        items, groups, unmatched = [], [], []
        for req in requests:
            if req.group and req.group not in groups:
                groups.append(req.group)
            if req.serial:
                entries = [CatalogEntry(serial=req.serial, name=req.name or "Item", label=req.label)]
            else:
                entries = self.f.catalog.search(SearchQuery(
                    query=req.query, type=req.type, element=req.element, manufacturer=req.manufacturer,
                    rarity=req.rarity, character=req.character, limit=req.count)).entries
            if not entries:
                unmatched.append(req.query or json.dumps({"type": req.type, "element": req.element}))
                continue
            for e in entries:
                serial = self.f.codec.relevel(e.serial, level) if level is not None else e.serial
                info = self.f.ops.describe(serial)
                items.append(LoadoutItem(
                    name=e.name, serial=serial, level=info.level, group=req.group,
                    display_name=req.display_name, manufacturer=e.manufacturer, label=e.label, type=e.type,
                    weapon_type=e.weapon_type, rarity=info.rarity or e.rarity, element=info.element,
                    category=info.category, legendary_name=info.legendary_name, note=req.note,
                    warnings=self.item_warnings))
        return Loadout(title=title, level=level, items=tuple(items), groups=tuple(groups),
                       unmatched=tuple(unmatched), warnings=self.loadout_warnings)


def fake_forge(forge, config=None, **fake_kwargs):
    fake = FakeBuilder(forge, **fake_kwargs)
    return Forge.build(config or forge.config, overrides={"builder": fake}, only=["builder", "render"]), fake


SPEC = [
    {"group": "Weapons", "query": D.SHOTGUN_Q, "type": "shotgun", "element": "cryo", "display_name": D.SHOTGUN_NAME,
     "note": "the <em>one</em>"},
    {"group": "Gear", "query": D.GEAR_Q, "element": "cryo"},
]


def test_build_inline_spec_writes_both_files_and_prints_the_summary(capsys, forge, tmp_path):
    bforge, fake = fake_forge(forge)
    out_html = tmp_path / "sheets" / "cryo.html"
    code, out, err = run(capsys, ["build", "--spec", json.dumps(SPEC), "--level", "60", "--title", "Cryo Loadout",
                                  "--out", str(out_html)], bforge)
    assert code == 0 and err == ""
    summary = json.loads(out)
    assert set(summary) == {"title", "level", "count", "html", "plain", "items", "unmatched", "warnings"}
    assert summary["title"] == "Cryo Loadout" and summary["level"] == 60 and summary["count"] == 2
    assert summary["html"] == os.path.abspath(out_html)
    assert summary["plain"] == os.path.abspath(tmp_path / "sheets" / "cryo.txt")
    assert summary["unmatched"] == [] and summary["warnings"] == []
    for item in summary["items"]:
        assert {"name", "category", "element", "rarity", "level", "serial", "warnings"} <= set(item)
        assert item["level"] == 60
    assert [i["element"] for i in summary["items"]] == ["cryo", None]       # weapon: decoded; gear: none
    html = out_html.read_text(encoding="utf-8")
    text = (tmp_path / "sheets" / "cryo.txt").read_text(encoding="utf-8")
    for item in summary["items"]:
        assert htmllib.escape(item["serial"]) in html and item["serial"] in text
    assert "Cryo Loadout" in html
    call = fake.calls[0]
    assert call["level"] == 60 and call["title"] == "Cryo Loadout"
    assert [r.group for r in call["requests"]] == ["Weapons", "Gear"]
    assert call["requests"][0].display_name == D.SHOTGUN_NAME and call["requests"][0].note == "the <em>one</em>"


def test_build_custom_plain_path(capsys, forge, tmp_path):
    bforge, _ = fake_forge(forge)
    code, out, err = run(capsys, ["build", "--spec", json.dumps(SPEC[:1]), "--out", str(tmp_path / "a.html"),
                                  "--plain", str(tmp_path / "codes.list")], bforge)
    assert code == 0
    assert Path(json.loads(out)["plain"]) == Path(os.path.abspath(tmp_path / "codes.list"))
    assert (tmp_path / "codes.list").exists() and not (tmp_path / "a.txt").exists()


def test_build_spec_from_file_bom_and_stdin(capsys, forge, tmp_path, monkeypatch):
    bforge, fake = fake_forge(forge)
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(SPEC), encoding="utf-8")
    code, out, err = run(capsys, ["build", "--spec", "@" + str(spec_file), "--out", str(tmp_path / "f.html")], bforge)
    assert code == 0 and json.loads(out)["count"] == 2
    bom_file = tmp_path / "bom.json"                       # what Windows editors/PowerShell write
    bom_file.write_bytes(b"\xef\xbb\xbf" + json.dumps(SPEC).encode("utf-8"))
    code, out, err = run(capsys, ["build", "--spec", "@" + str(bom_file), "--out", str(tmp_path / "g.html")], bforge)
    assert code == 0 and json.loads(out)["count"] == 2
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(SPEC)))
    code, out, err = run(capsys, ["build", "--spec", "-", "--out", str(tmp_path / "h.html")], bforge)
    assert code == 0 and json.loads(out)["count"] == 2
    assert len(fake.calls) == 3


def test_build_explicit_serial_entries(capsys, forge, serials, tmp_path):
    bforge, fake = fake_forge(forge)
    spec = [{"group": "Gear", "serial": serials["shield"] + "  ", "display_name": "Mine", "label": "Shield", "name": "X"}]
    code, out, err = run(capsys, ["build", "--spec", json.dumps(spec), "--out", str(tmp_path / "e.html")], bforge)
    assert code == 0, err
    item = json.loads(out)["items"][0]
    assert item["display_name"] == "Mine" and item["group"] == "Gear" and item["level"] == 60
    assert fake.calls[0]["requests"][0].serial == serials["shield"]         # stray whitespace is trimmed


def test_build_defaults_level_from_config(capsys, forge, tmp_path):
    bforge, fake = fake_forge(forge)
    spec = json.dumps(SPEC[:1])
    run(capsys, ["build", "--spec", spec, "--out", str(tmp_path / "a.html")], bforge)
    run(capsys, ["build", "--spec", spec, "--out", str(tmp_path / "b.html"), "--level", "45"], bforge)
    run(capsys, ["build", "--spec", spec, "--out", str(tmp_path / "c.html"), "--no-relevel"], bforge)
    assert [c["level"] for c in fake.calls] == [60, 45, None]
    assert [c["title"] for c in fake.calls] == ["Break Free Loadout"] * 3

    cfg = Config.load(path=write_cfg(tmp_path, "[forge]\nlevel = 55\n"))
    bforge55, fake55 = fake_forge(forge, config=cfg)
    code, out, err = run(capsys, ["build", "--spec", spec, "--out", str(tmp_path / "d.html")], bforge55)
    assert fake55.calls[0]["level"] == 55 and json.loads(out)["level"] == 55

    code, out, err = run(capsys, ["build", "--spec", spec, "--out", str(tmp_path / "e.html"),
                                  "--level", "60", "--no-relevel"], bforge)
    assert code == 2 and "not allowed with" in err


def test_build_classmod_gets_the_configured_character(capsys, forge, tmp_path):
    bforge, fake = fake_forge(forge)
    spec = [{"type": "classmod"}, {"type": "classmod", "character": "paladin"}, {"type": "shotgun", "element": "cryo"}]
    code, out, err = run(capsys, ["build", "--spec", json.dumps(spec), "--out", str(tmp_path / "c.html")], bforge)
    assert code == 0
    reqs = fake.calls[0]["requests"]
    assert [r.character for r in reqs] == ["gravitar", "paladin", None]
    assert "spec entry 1" in err and "gravitar" in err and "spec entry 2" not in err


def test_build_reports_unmatched_but_still_succeeds(capsys, forge, tmp_path):
    bforge, _ = fake_forge(forge)
    spec = [SPEC[0], {"group": "Gear", "query": "zzznotanitem"}]
    code, out, err = run(capsys, ["build", "--spec", json.dumps(spec), "--out", str(tmp_path / "u.html")], bforge)
    assert code == 0
    assert json.loads(out)["unmatched"] == ["zzznotanitem"] and json.loads(out)["count"] == 1
    assert "unmatched: zzznotanitem" in err


def test_build_with_nothing_resolved_exits_3_and_writes_nothing(capsys, forge, tmp_path):
    bforge, _ = fake_forge(forge)
    target = tmp_path / "none.html"
    code, out, err = run(capsys, ["build", "--spec", json.dumps([{"query": "zzznotanitem"}, {"query": "alsonot"}]),
                                  "--out", str(target)], bforge)
    assert code == 3 and out == "" and "Traceback" not in err
    assert "error: no items resolved from spec" in err
    assert "unmatched: zzznotanitem" in err and "unmatched: alsonot" in err
    assert not target.exists() and not (tmp_path / "none.txt").exists()


def test_build_reports_warnings_everywhere(capsys, forge, tmp_path):
    bforge, _ = fake_forge(forge, loadout_warnings=["catalog is a bit stale"], item_warnings=["level did not take"])
    code, out, err = run(capsys, ["build", "--spec", json.dumps(SPEC[:1]), "--out", str(tmp_path / "w.html")], bforge)
    assert code == 0
    summary = json.loads(out)
    assert summary["warnings"] == ["catalog is a bit stale", "level did not take"]
    assert summary["items"][0]["warnings"] == ["level did not take"]
    assert "warning: catalog is a bit stale" in err
    assert "warning: %s: level did not take" % D.SHOTGUN_NAME in err
    assert "level did not take" in (tmp_path / "w.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("spec,needle", [
    ("not json at all", "not valid JSON"),
    ('{"query": "anarchy"}', "JSON array"),
    ("[]", "spec is empty"),
    ('["anarchy"]', "spec entry 1: must be a JSON object"),
    ('[{"query": "anarchy", "count": 0}]', "count must be >= 1"),
    ('[{"query": "anarchy", "count": "lots"}]', "spec entry 1: invalid"),
    ('[{"query": 5}]', "'query' must be a string"),
    ('[{"group": "Weapons"}]', "needs a 'serial' or at least one search field"),
    ('[{"query": "anarchy", "element": "plasma"}]', "spec entry 1: unknown element 'plasma'"),
    ('[{"query": "ok"}, {"element": "plasma"}]', "spec entry 2"),
    ("@/definitely/not/here.json", "cannot read spec file"),
])
def test_build_bad_specs_are_clean_errors(capsys, forge, tmp_path, spec, needle):
    bforge, fake = fake_forge(forge)
    target = tmp_path / "bad.html"
    code, out, err = run(capsys, ["build", "--spec", spec, "--out", str(target)], bforge)
    assert_clean_failure(code, out, err, needle=needle)
    assert out == "" and fake.calls == [] and not target.exists()


def test_build_warns_about_unknown_spec_keys(capsys, forge, tmp_path):
    bforge, fake = fake_forge(forge)
    spec = [{"query": D.SHOTGUN_Q, "elemnt": "cryo", "weaponType": "shotgun", "label_name": D.SHOTGUN_NAME}]
    code, out, err = run(capsys, ["build", "--spec", json.dumps(spec), "--out", str(tmp_path / "k.html")], bforge)
    assert code == 0
    assert "warning: spec entry 1: ignoring unknown key(s): elemnt, weaponType" in err
    assert fake.calls[0]["requests"][0].display_name == D.SHOTGUN_NAME       # legacy label_name still understood


def test_build_unwritable_output_is_a_clean_error(capsys, forge, tmp_path):
    bforge, _ = fake_forge(forge)
    # --out ending in .txt with no --plain would overwrite the sheet with the list: render refuses
    code, out, err = run(capsys, ["build", "--spec", json.dumps(SPEC[:1]), "--out", str(tmp_path / "x.txt")], bforge)
    assert_clean_failure(code, out, err, needle="cannot write output")
    blocker = tmp_path / "afile"
    blocker.write_text("x")
    code, out, err = run(capsys, ["build", "--spec", json.dumps(SPEC[:1]), "--out", str(blocker / "sub" / "x.html")], bforge)
    assert_clean_failure(code, out, err, needle="cannot write output")


def test_build_with_unimplemented_builder_is_module_unavailable(capsys, forge, tmp_path):
    err_ = NotImplementedError("module 'builder' has not implemented build yet")
    bforge, _ = fake_forge(forge, error=err_)
    code, out, err = run(capsys, ["build", "--spec", json.dumps(SPEC[:1]), "--out", str(tmp_path / "n.html")], bforge)
    assert_clean_failure(code, out, err, expect_code=4, needle="has not implemented build yet")
    assert "bl4forge doctor" in err


def test_unexpected_exceptions_are_reported_not_dumped(capsys, forge, tmp_path):
    bforge, _ = fake_forge(forge, error=RuntimeError("kaboom"))
    argv = ["build", "--spec", json.dumps(SPEC[:1]), "--out", str(tmp_path / "x.html")]
    code, out, err = run(capsys, argv, bforge)
    assert code == 5 and "Traceback" not in err
    assert "internal error: RuntimeError: kaboom" in err and "--debug" in err
    code, out, err = run(capsys, argv + ["--debug"], bforge)
    assert code == 5 and "Traceback" in err


def test_build_with_a_failed_builder_is_module_unavailable(capsys, config, tmp_path):
    class BrokenBuilder(Module):
        name = "builder"
        purpose = "fails"
        requires = ("catalog", "ops")

        def __init__(self, ctx):
            raise RuntimeError("builder exploded")

    forge = Forge.build(config, overrides={"builder": BrokenBuilder}, only=["builder", "render"])
    code, out, err = run(capsys, ["build", "--spec", json.dumps(SPEC[:1]), "--out", str(tmp_path / "x.html")], forge)
    assert_clean_failure(code, out, err, expect_code=4, needle="module 'builder'")
    assert "builder exploded" in err and "bl4forge doctor" in err


def test_build_degraded_builder_warns_once(capsys, forge, tmp_path):
    bforge, _ = fake_forge(forge)
    bforge.states["builder"].state = "degraded"
    bforge.states["builder"].detail = "not implemented yet"
    code, out, err = run(capsys, ["build", "--spec", json.dumps(SPEC[:1]), "--out", str(tmp_path / "d.html")], bforge)
    assert code == 0
    assert err.count("module 'builder' is degraded (not implemented yet)") == 1


# ---- build (real builder; runs when the builder module is healthy) -----------------------------------

README_EXAMPLES = {
    "cryo loadout": [
        {"group": "Weapons", "type": "shotgun", "element": "cryo", "query": D.SHOTGUN_Q},
        {"group": "Weapons", "type": "sniper", "element": "cryo"},
        {"group": "Gear", "query": D.GEAR_Q, "element": "cryo"},
        {"group": "Gear", "type": "classmod"},
        {"group": "Gear", "type": "repkit"},
        {"group": "Gear", "type": "grenade"},
    ],
    "wombo combo + plasma coil + cryo super soldier": [
        {"group": "Weapons", "query": D.WOMBO_Q, "element": "cryo"},
        {"group": "Weapons", "query": D.PLASMA_Q},
        {"group": "Gear", "query": D.GEAR_Q, "element": "cryo"},
    ],
    "level 60 radiation shotgun": [
        {"type": "shotgun", "element": "radiation"},
    ],
}


@pytest.mark.parametrize("name", list(README_EXAMPLES))
def test_build_with_real_builder(capsys, forge, tmp_path, name):
    if forge.states["builder"].state != "ok":
        pytest.skip("builder is %s (%s)" % (forge.states["builder"].state, forge.states["builder"].detail))
    spec = README_EXAMPLES[name]
    target = tmp_path / "loadout.html"
    code, out, err = run(capsys, ["build", "--spec", json.dumps(spec), "--level", "60",
                                  "--title", name, "--out", str(target)], forge)
    assert code == 0, err
    summary = json.loads(out)
    assert summary["unmatched"] == []
    assert summary["count"] >= len(spec)
    assert summary["level"] == 60
    for item in summary["items"]:
        assert item["level"] == 60 and item["serial"].startswith("@U")
        assert forge.codec.get_level(forge.codec.decode(item["serial"])) == 60
    html = target.read_text(encoding="utf-8")
    text = (tmp_path / "loadout.txt").read_text(encoding="utf-8")
    for item in summary["items"]:
        assert htmllib.escape(item["serial"]) in html and item["serial"] in text
