"""Edge cases for the `data` module: read-only containers, health, version, deviations from legacy."""
from __future__ import annotations

import copy
import dataclasses
import json
import pickle
from collections.abc import Mapping
from pathlib import Path

import pytest

from bl4forge.core.module import ModuleContext
from bl4forge.modules.data import DataModule
from bl4forge.modules.data._frozen import FrozenDict, FrozenList, freeze

FAKE_CAT = 4242      # not a category in the real manifest


def make(config, data_dir=None) -> DataModule:
    cfg = config if data_dir is None else dataclasses.replace(config, data_dir=Path(data_dir))
    return DataModule(ModuleContext("data", cfg, {}))


def write_fake_manifest(data_dir: Path, tag: str = "a") -> Path:
    m = Path(data_dir) / "manifest"
    (m / "parts").mkdir(parents=True)
    (m / "parts" / ("gun_%s-%d.tsv" % (tag, FAKE_CAT))).write_text(
        "index\tname\n1\tpart_%s_one\n2\tcomp_05_legendary_zed_%s\n" % (tag, tag), encoding="utf-8")
    (m / "category_names.tsv").write_text("category_id\tname\n%d\t%s SMG\n" % (FAKE_CAT, tag.upper()), encoding="utf-8")
    (m / "item_names.tsv").write_text("np_zed_%s\tZed Prime %s\n" % (tag, tag.upper()), encoding="utf-8")
    (m / "part_meta.json").write_text(json.dumps({"%d:2" % FAKE_CAT: {"name": "Zed", "rarity": "Pearl"}}), encoding="utf-8")
    (m / "drops.json").write_text(json.dumps({"version": 1, "drops": [{"item_name": "Zed"}]}), encoding="utf-8")
    return m


@pytest.fixture(scope="module")
def mod(config):
    return make(config)


# ---- read-only containers -------------------------------------------------------------------------

def test_frozen_containers_behave_like_dict_and_list_but_refuse_mutation():
    data = freeze({"a": [1, {"b": 2}], "c": {"d": [3]}})
    assert isinstance(data, dict) and isinstance(data, Mapping) and isinstance(data["a"], list)
    assert data == {"a": [1, {"b": 2}], "c": {"d": [3]}}
    assert json.loads(json.dumps(data)) == {"a": [1, {"b": 2}], "c": {"d": [3]}}
    for op in (lambda: data.__setitem__("x", 1), lambda: data.update(x=1), lambda: data.__ior__({"x": 1}),
               lambda: data["a"].__iadd__([9]), lambda: data["a"].__imul__(2),
               lambda: data["a"][1].__setitem__("b", 3), lambda: data["c"]["d"].append(4)):
        with pytest.raises(TypeError):
            op()
    assert data == {"a": [1, {"b": 2}], "c": {"d": [3]}}


def test_frozen_copies_are_plain_and_mutable(mod):
    for dup in (copy.copy(mod.drops()), copy.deepcopy(mod.drops()), pickle.loads(pickle.dumps(mod.drops())),
                dict(mod.drops()), mod.drops().copy()):
        assert type(dup) is dict
    deep = copy.deepcopy(mod.drops())
    assert type(deep["drops"]) is list and type(deep["drops"][0]) is dict
    deep["drops"].append("scratch")
    deep["drops"][0]["item_name"] = "changed"
    assert "scratch" not in mod.drops()["drops"] and mod.drops()["drops"][0]["item_name"] != "changed"
    lst = mod.drops()["drops"]
    assert type(copy.copy(lst)) is list and type(list(lst)) is list and type(lst.copy()) is list
    assert type(pickle.loads(pickle.dumps(lst))) is list
    assert type(lst + [1]) is list


def test_frozen_types_can_be_built_empty():
    assert FrozenDict() == {} and FrozenList() == []
    with pytest.raises(TypeError):
        FrozenList().append(1)


# ---- prettify edge cases ---------------------------------------------------------------------------

def test_prettify_never_raises_on_odd_input(mod):
    assert mod.prettify_part(None) == ""
    assert mod.prettify_part("") == ""
    assert mod.prettify_part(123) == "123"
    assert mod.prettify_legendary(None) is None
    assert mod.prettify_legendary("") is None
    assert mod.prettify_legendary("04") is None            # class-mod slot index, not a name


def test_prettify_documented_values(mod):
    assert mod.prettify_part("part_scope_02_lens_02") == "Scope 02 Lens 02"
    assert mod.prettify_part("comp_05_legendary_04") == "Legendary"
    assert mod.prettify_part("comp_09_weird_thing") == "Weird — Thing"      # tier outside the ladder
    assert mod.prettify_legendary("hellwalker") == mod.item_names().get("np_hellwalker", "Hellwalker")


# ---- known legacy quirk, preserved on purpose ---------------------------------------------------------

def test_is_weapon_category_keeps_legacy_substring_quirk(mod):
    """Legacy matches the weapon word ' ar' as a substring, so ' armor' and ' arms' count: three
    non-weapon categories read as weapons. Preserved for parity (none is an item category in the
    9,875-serial database); see CONTRACT.md 'Deviations' and docs/CHANGE_REQUESTS.md."""
    weapon_words = {"pistol", "shotgun", "smg", "sniper", "ar", "assault", "weapon"}
    quirky = {cid for cid, name in mod.category_names().items()
              if mod.is_weapon_category(cid) and not weapon_words & set(name.lower().split())}
    assert quirky == {145, 236, 237}
    assert [mod.category_names()[c] for c in sorted(quirky)] == [
        "Def Sumofhisparts Arms", "Shield Armor Pickup", "Armor Shield"]
    # and the ordinary cases are right
    assert mod.is_weapon_category(21) and mod.is_weapon_category(1)          # Maliwan SMG, Weapon
    assert not mod.is_weapon_category(279)                                   # Maliwan Shield
    assert not mod.is_weapon_category(90)                                    # Ammo Smg


# ---- health -------------------------------------------------------------------------------------

def test_health_flags_duplicate_and_unrecognised_part_files(config, tmp_path):
    m = write_fake_manifest(tmp_path)
    (m / "parts" / ("other_gun-%d.tsv" % FAKE_CAT)).write_text("index\tname\n1\tx\n", encoding="utf-8")
    (m / "parts" / "notes.tsv").write_text("index\tname\n", encoding="utf-8")
    rep = make(config, tmp_path).health()
    bad = {c.name: c.detail for c in rep.checks if not c.ok}
    assert set(bad) == {"part_tables"}
    assert "duplicate" in bad["part_tables"] and "notes.tsv" in bad["part_tables"]


def test_health_ok_on_a_clean_small_manifest(config, tmp_path):
    write_fake_manifest(tmp_path)
    rep = make(config, tmp_path).health()
    assert rep.ok, [c for c in rep.checks if not c.ok]
    assert "1 part tables for 1 .tsv files" in {c.name: c.detail for c in rep.checks}["part_tables"]


def test_health_reports_unreadable_files(config, tmp_path):
    m = write_fake_manifest(tmp_path)
    (m / "part_meta.json").write_text("{broken", encoding="utf-8")
    rep = make(config, tmp_path).health()
    checks = {c.name: c for c in rep.checks}
    assert not rep.ok and not checks["part_meta"].ok and not checks["files_readable"].ok
    assert "part_meta" in checks["files_readable"].detail


def test_health_never_raises(config, monkeypatch):
    m = make(config)
    monkeypatch.setattr(m, "_health", lambda: 1 / 0)
    rep = m.health()
    assert rep.ok is False and "ZeroDivisionError" in rep.summary


# ---- manifest_version ---------------------------------------------------------------------------

def test_manifest_version_real_data(mod, config):
    """The shipped manifest records no extract date (drops.json's `version: 1` is a schema number),
    so the answer is 'unknown' unless a VERSION marker file has been added next to the data."""
    marker = config.manifest_dir / "VERSION"
    if marker.is_file():
        lines = [ln.strip() for ln in marker.read_text(encoding="utf-8").splitlines()]
        assert mod.manifest_version() == next(ln for ln in lines if ln and not ln.startswith("#"))
    else:
        assert mod.manifest_version() == "unknown"
    assert json.loads((config.manifest_dir / "drops.json").read_text(encoding="utf-8"))["version"] == 1


def test_manifest_version_reads_marker_file(config, tmp_path):
    m = write_fake_manifest(tmp_path)
    assert make(config, tmp_path).manifest_version() == "unknown"
    (m / "VERSION").write_text("# extract date\n\n  2026-08-01  \nignored\n", encoding="utf-8")
    assert make(config, tmp_path).manifest_version() == "2026-08-01"
    (m / "VERSION").write_text("\n# only a comment\n", encoding="utf-8")
    assert make(config, tmp_path).manifest_version() == "unknown"
