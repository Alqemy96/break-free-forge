"""Tests for the `data` module: CONTRACT invariants + full parity with the legacy partsdb.

Legacy (`legacy.partsdb`) is the oracle. Intentional differences are listed in
src/bl4forge/modules/data/CONTRACT.md "Deviations from legacy" and exercised in test_data_edges.py.
"""
from __future__ import annotations

import dataclasses
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from bl4forge.core.config import Config
from bl4forge.core.errors import DataMissing
from bl4forge.core.forge import OK, Forge
from bl4forge.core.module import ModuleContext, conformance_problems
from bl4forge.core.ports import DataPort
from bl4forge.core.registry import Registry
from bl4forge.modules.data import MODULE, DataModule

EXTRA_CATEGORY_IDS = [0, -1, 999999, None, "21", 21.5]     # ids that are not in the manifest
FAKE_CAT = 4242                                               # not a category in the real manifest


# ---- helpers ----------------------------------------------------------------------------------

def make(config: Config, data_dir=None) -> DataModule:
    """A DataModule on its own context. Never mutates the shared session config."""
    cfg = config if data_dir is None else dataclasses.replace(config, data_dir=Path(data_dir))
    return DataModule(ModuleContext("data", cfg, {}))


def write_fake_manifest(data_dir: Path, tag: str = "a") -> Path:
    """A tiny but complete manifest whose content depends on `tag` (category FAKE_CAT is not a real one)."""
    m = Path(data_dir) / "manifest"
    (m / "parts").mkdir(parents=True)
    (m / "parts" / ("gun_%s-%d.tsv" % (tag, FAKE_CAT))).write_text(
        "index\tname\n1\tpart_%s_one\n2\tcomp_05_legendary_zed_%s\n3\tcomp_05_legendary_plain\n" % (tag, tag),
        encoding="utf-8")
    (m / "category_names.tsv").write_text(
        "category_id\tname\n%d\t%s SMG\n%d\tVladof Shield\n" % (FAKE_CAT, tag.upper(), FAKE_CAT + 1),
        encoding="utf-8")
    (m / "item_names.tsv").write_text("np_zed_%s\tZed Prime %s\n" % (tag, tag.upper()), encoding="utf-8")
    (m / "part_meta.json").write_text(json.dumps(
        {"%d:2" % FAKE_CAT: {"name": "Zed " + tag, "rarity": "Pearl", "pack": "bounty_pack_9"}}), encoding="utf-8")
    (m / "drops.json").write_text(json.dumps(
        {"version": 1, "drops": [{"item_name": "Zed_%s" % tag, "source": "Boss"}], "probabilities": {}}),
        encoding="utf-8")
    return m


@pytest.fixture(scope="module")
def mod(config) -> DataModule:
    return make(config)


@pytest.fixture(scope="module")
def raw_meta(config) -> dict:
    """part_meta.json read straight from disk, independent of the module and of legacy."""
    return json.loads((config.manifest_dir / "part_meta.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def category_ids(legacy):
    ids = set(legacy.partsdb.category_names()) | set(legacy.partsdb._category_files())
    return sorted(ids)


@pytest.fixture(scope="module")
def all_refs(legacy, category_ids):
    """Every (category_id, index) that has a row in some parts table (per the legacy reader)."""
    return [(c, i) for c in category_ids for i in legacy.partsdb.part_table(c)]


@pytest.fixture(scope="module")
def serial_refs(legacy, all_serials):
    """Every (category_id, index, raw) legacy resolved across the whole serial database, plus
    every item category id seen. 9,875 serials."""
    refs, cats = set(), set()
    for s in all_serials:
        info = legacy.partsdb.describe(s)
        cats.add(info["category_id"])
        for r in info["parts"]:
            refs.add((r.category_id, r.index, r.raw))
    return refs, cats


# ---- the oracle and the data dir must agree before parity means anything -------------------------

def test_legacy_manifest_copy_is_identical_to_data_dir(config, legacy):
    ours, theirs = Path(config.manifest_dir), Path(legacy.partsdb.MANIFEST_DIR)
    # VERSION is the one file we add on top of the legacy copy (the extract date); everything else is identical.
    rel = lambda root: {p.relative_to(root): p.read_bytes() for p in root.rglob("*")  # noqa: E731
                        if p.is_file() and p.name != "VERSION"}
    a, b = rel(ours), rel(theirs)
    assert set(a) == set(b), "file lists differ between data/manifest and the legacy copy"
    assert [k for k in a if a[k] != b[k]] == [], "these manifest files differ from the legacy copy"


# ---- port conformance and wiring -----------------------------------------------------------------

def test_module_is_exported_and_conforms_to_port(mod):
    assert MODULE is DataModule
    assert (DataModule.name, DataModule.requires, DataModule.port) == ("data", (), DataPort)
    assert conformance_problems(mod, DataPort) == []
    assert isinstance(mod, DataPort)


def test_forge_starts_data_ok(config):
    forge = Forge.build(config, registry=Registry([DataModule]))
    assert forge.states["data"].state == OK, forge.states["data"].detail
    assert isinstance(forge.data, DataModule)


def test_health_ok_on_real_data(mod, config):
    rep = mod.health()
    assert rep.ok, rep
    checks = {c.name: c for c in rep.checks}
    assert {"available", "category_names", "part_tables", "part_meta"} <= set(checks)
    on_disk = len(list((config.manifest_dir / "parts").glob("*.tsv")))
    assert "%d part tables for %d .tsv files" % (on_disk, on_disk) in checks["part_tables"].detail


# ---- invariant: lookups_never_raise_when_missing -------------------------------------------------

def assert_everything_empty(m: DataModule):
    assert m.available() is False
    assert m.category_names() == {}
    assert m.part_table(21) == {} and m.part_table(None) == {} and m.part_table([]) == {}
    assert m.item_names() == {}
    assert m.part_meta(26, 84) == {} and m.part_meta(None, None) == {}
    assert m.drops() == {}
    assert m.drops_by_item() == {}
    assert m.is_weapon_category(21) is False and m.is_weapon_category(None) is False
    assert m.manifest_version() == "unknown"


def test_lookups_never_raise_when_missing(config, tmp_path):
    m = make(config, tmp_path)                    # tmp_path is empty: no manifest/ at all
    assert_everything_empty(m)
    with pytest.raises(DataMissing):
        m.require()
    # labels are pure and keep working without data (item-name table just stays empty)
    assert m.prettify_part("part_scope_02_lens_02") == "Scope 02 Lens 02"
    assert m.prettify_legendary("hellwalker") == "Hellwalker"
    assert m.prettify_part("comp_05_legendary_hellwalker") == "Legendary — Hellwalker"
    rep = m.health()                              # never raises, reports the problem
    assert rep.ok is False and "not found" in rep.summary


def test_require_passes_when_present(mod):
    assert mod.require() is None


def test_manifest_dir_that_does_not_exist_at_all(config, tmp_path):
    m = make(config, tmp_path / "nope" / "deeper")
    assert_everything_empty(m)


def test_partial_manifest_is_degraded_not_fatal(config, tmp_path):
    """parts/ exists but every other file is missing: lookups return empties, health says why."""
    (tmp_path / "manifest" / "parts").mkdir(parents=True)
    m = make(config, tmp_path)
    assert m.available() is True
    assert m.require() is None
    assert m.category_names() == {} and m.item_names() == {} and m.drops() == {}
    assert m.drops_by_item() == {} and m.part_meta(1, 1) == {} and m.part_table(1) == {}
    assert m.is_weapon_category(1) is False
    rep = m.health()
    assert rep.ok is False
    assert {c.name for c in rep.checks if not c.ok} >= {"category_names", "part_tables", "part_meta"}


@pytest.mark.parametrize("fname, junk", [
    ("category_names.tsv", b"\xff\xfe\x00 not a table \x00\x01"),
    ("item_names.tsv", b"\xff\xfe\x00\x00"),
    ("part_meta.json", b"{not json"),
    ("part_meta.json", b"[1, 2, 3]"),
    ("drops.json", b"{not json"),
    ("drops.json", b'["a list, not an object"]'),
    ("parts/gun_a-4242.tsv", b"\x00\x00\x00"),
])
def test_corrupt_files_do_not_raise(config, tmp_path, fname, junk):
    m = write_fake_manifest(tmp_path)
    (m / fname).write_bytes(junk)
    mod = make(config, tmp_path)
    for call in (mod.category_names, mod.item_names, mod.drops, mod.drops_by_item):
        call()
    mod.part_table(FAKE_CAT), mod.part_meta(FAKE_CAT, 2), mod.is_weapon_category(FAKE_CAT)
    mod.prettify_part("comp_05_legendary_zed_a"), mod.prettify_legendary("zed_a")
    assert isinstance(mod.health().ok, bool)


def test_data_that_appears_later_is_picked_up(config, tmp_path):
    m = make(config, tmp_path)
    assert m.available() is False and m.category_names() == {}
    write_fake_manifest(tmp_path)                 # nothing was cached while the manifest was absent
    assert m.available() is True
    assert dict(m.category_names()) == {FAKE_CAT: "A SMG", FAKE_CAT + 1: "Vladof Shield"}
    assert dict(m.part_table(FAKE_CAT)) == {1: "part_a_one", 2: "comp_05_legendary_zed_a",
                                            3: "comp_05_legendary_plain"}


# ---- invariant: rarity_and_pack_from_part_meta ----------------------------------------------------

def test_rarity_and_pack_from_part_meta_real_pearl(mod):
    """comp_05_legendary_temper (26:84) is named 'legendary' but the game tags it Pearl."""
    assert mod.part_table(26)[84] == "comp_05_legendary_temper"
    meta = mod.part_meta(26, 84)
    assert meta["rarity"] == "Pearl"
    assert meta["name"] == "Solar Temper"
    assert "pack" not in meta                     # absent means base game; rules does the defaulting
    # a pearl that also carries a DLC pack: explicit fields, not guessed
    assert mod.part_table(13)[91] == "comp_05_legendary_kaos"
    assert (mod.part_meta(13, 91)["rarity"], mod.part_meta(13, 91)["pack"]) == ("Pearl", "bounty_pack_4")


def test_every_pearl_is_reported_as_pearl_whatever_its_name(mod, raw_meta):
    pearls = [k for k, v in raw_meta.items() if v.get("rarity") == "Pearl"]
    named_legendary = []
    for key in pearls:
        cat, idx = map(int, key.split(":"))
        assert mod.part_meta(cat, idx)["rarity"] == "Pearl"
        if mod.part_table(cat)[idx].startswith("comp_05_legendary"):
            named_legendary.append(key)
    assert len(pearls) == 20 and len(named_legendary) == 14      # the hard-won fact, from the data


def test_part_meta_is_exactly_the_explicit_fields_nothing_inferred(mod, raw_meta, category_ids):
    """For every part ref: the entry is part_meta.json's entry verbatim. In particular no 'rarity'
    appears for a part that merely has 'legendary' in its name (94 such comp_05_legendary_* parts)."""
    unlabelled = 0
    for cat in category_ids:
        for idx, raw in mod.part_table(cat).items():
            entry = mod.part_meta(cat, idx)
            assert entry == raw_meta.get("%d:%d" % (cat, idx), {})
            if raw.startswith("comp_05_legendary") and "rarity" not in entry:
                unlabelled += 1
    assert unlabelled > 0
    assert mod.part_meta(999999, 1) == {} and mod.part_meta(None, None) == {}


def test_prettify_prefix_is_a_label_not_a_rarity_source(mod):
    """prettify_part keeps the legacy name-token label ('Legendary - Temper'); part_meta is the
    authority and says Pearl. Callers must take rarity from part_meta only."""
    assert mod.prettify_part("comp_05_legendary_temper").startswith("Legendary")
    assert mod.part_meta(26, 84)["rarity"] == "Pearl"


def test_fake_manifest_rarity_comes_from_meta_not_name(config, tmp_path):
    write_fake_manifest(tmp_path)
    m = make(config, tmp_path)
    assert m.part_meta(FAKE_CAT, 2) == {"name": "Zed a", "rarity": "Pearl", "pack": "bounty_pack_9"}
    assert m.part_table(FAKE_CAT)[3] == "comp_05_legendary_plain"
    assert m.part_meta(FAKE_CAT, 3) == {}                # name says legendary; data says nothing -> nothing


# ---- invariant: per_instance_cache ---------------------------------------------------------------

def test_per_instance_cache_two_data_dirs_do_not_interfere(config, tmp_path):
    da, db = tmp_path / "a", tmp_path / "b"
    da.mkdir(), db.mkdir()
    write_fake_manifest(da, "a")
    write_fake_manifest(db, "b")
    real, a, b = make(config), make(config, da), make(config, db)
    for _ in range(2):                            # interleave, twice, so any shared cache would show
        assert a.category_names()[FAKE_CAT] == "A SMG"
        assert b.category_names()[FAKE_CAT] == "B SMG"
        assert 21 in real.category_names() and FAKE_CAT not in real.category_names()
        assert a.part_table(FAKE_CAT)[1] == "part_a_one" and b.part_table(FAKE_CAT)[1] == "part_b_one"
        assert real.part_table(FAKE_CAT) == {} and a.part_table(21) == {} and real.part_table(21) != {}
        assert a.item_names() == {"np_zed_a": "Zed Prime A"} and b.item_names() == {"np_zed_b": "Zed Prime B"}
        assert a.part_meta(FAKE_CAT, 2)["name"] == "Zed a" and b.part_meta(FAKE_CAT, 2)["name"] == "Zed b"
        assert real.part_meta(FAKE_CAT, 2) == {}
        assert list(a.drops_by_item()) == ["zed_a"] and list(b.drops_by_item()) == ["zed_b"]
        assert a.drops()["drops"][0]["item_name"] == "Zed_a"
        assert a.is_weapon_category(FAKE_CAT) and not a.is_weapon_category(FAKE_CAT + 1)
    # the cache is per instance: editing a's files on disk after loading does not change what a serves
    (da / "manifest" / "category_names.tsv").write_text(
        "category_id\tname\n%d\tCHANGED\n" % FAKE_CAT, encoding="utf-8")
    assert a.category_names()[FAKE_CAT] == "A SMG"
    assert make(config, da).category_names()[FAKE_CAT] == "CHANGED"    # a new instance sees the new file


def test_prettify_uses_this_instances_name_table(config, tmp_path):
    da, db = tmp_path / "a", tmp_path / "b"
    da.mkdir(), db.mkdir()
    write_fake_manifest(da, "a")
    write_fake_manifest(db, "b")
    a, b = make(config, da), make(config, db)
    assert a.prettify_legendary("zed_a") == "Zed Prime A"      # from a's item_names.tsv
    assert b.prettify_legendary("zed_a") == "Zed A"            # b has no such entry: title-case fallback
    assert b.prettify_legendary("zed_b") == "Zed Prime B"
    assert a.prettify_part("comp_05_legendary_zed_a") == "Legendary \u2014 Zed Prime A"
    assert b.prettify_part("comp_05_legendary_zed_a") == "Legendary \u2014 Zed A"


def test_manifest_dir_comes_from_config_not_from_file_location():
    pkg = Path(__file__).resolve().parents[2] / "src" / "bl4forge" / "modules" / "data"
    for f in pkg.glob("*.py"):
        assert "__file__" not in f.read_text(encoding="utf-8"), "%s derives a path from __file__" % f.name


def test_no_module_level_mutable_state():
    import importlib
    from bl4forge.modules.data._frozen import FrozenDict, FrozenList
    for name in ("", "._frozen", "._names", "._tsv"):
        module = importlib.import_module("bl4forge.modules.data" + name)
        for var, value in vars(module).items():
            if var.startswith("__"):
                continue
            assert not isinstance(value, (set, bytearray)), (name, var)
            if isinstance(value, (dict, list)):
                assert isinstance(value, (FrozenDict, FrozenList)), "%s%s.%s is mutable module state" % (
                    "data", name, var)


def test_concurrent_first_use_loads_once_and_agrees(config):
    m = make(config)
    def grab(_):
        return (m.category_names(), m.part_table(21), m.item_names(), m.drops(), m.drops_by_item(),
                m.part_meta(26, 84))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(grab, range(32)))
    first = results[0]
    for r in results[1:]:
        assert all(x is y for x, y in zip(first, r))


# ---- read-only ----------------------------------------------------------------------------------

def test_returned_mappings_are_read_only(mod):
    some_item = next(iter(mod.drops_by_item()))
    first_drop = mod.drops()["drops"][0]
    targets = [
        mod.category_names(), mod.part_table(21), mod.item_names(), mod.drops(), mod.drops_by_item(),
        mod.part_meta(26, 84), mod.part_meta(26, 84)["tags"], mod.drops()["drops"], first_drop,
        mod.drops_by_item()[some_item], mod.drops()["probabilities"],
        mod.part_table(999999), mod.part_meta(999999, 1),       # even the shared empties
    ]
    for t in targets:
        if isinstance(t, dict):
            for op in (lambda: t.__setitem__("zz", 1), lambda: t.update({"zz": 1}), lambda: t.pop("zz", None),
                       lambda: t.setdefault("zz", 1), lambda: t.clear(), lambda: t.popitem(),
                       lambda: t.__delitem__("zz")):
                with pytest.raises(TypeError):
                    op()
        else:
            for op in (lambda: t.append(1), lambda: t.extend([1]), lambda: t.insert(0, 1),
                       lambda: t.__setitem__(0, 1), lambda: t.pop(), lambda: t.clear(),
                       lambda: t.sort(), lambda: t.reverse(), lambda: t.remove(t[0])):
                with pytest.raises(TypeError):
                    op()
    assert 21 in mod.category_names()            # and nothing got through


# ---- matches_legacy ------------------------------------------------------------------------------

def test_matches_legacy_category_names(mod, legacy):
    assert dict(mod.category_names()) == legacy.partsdb.category_names()
    assert len(mod.category_names()) > 0
    assert all(type(k) is int for k in mod.category_names())


def test_matches_legacy_part_table_every_category(mod, legacy, category_ids):
    assert len(legacy.partsdb._category_files()) > 0
    non_empty = 0
    for cid in category_ids + EXTRA_CATEGORY_IDS:
        theirs = legacy.partsdb.part_table(cid) if not isinstance(cid, (list, dict)) else {}
        ours = mod.part_table(cid)
        assert dict(ours) == theirs, cid
        non_empty += bool(ours)
    assert non_empty == len(legacy.partsdb._category_files())     # 161 on the shipped extract
    assert all(type(k) is int for k in mod.part_table(21))


def test_matches_legacy_item_names(mod, legacy):
    assert dict(mod.item_names()) == legacy.partsdb.item_names()
    assert len(mod.item_names()) > 0


def test_matches_legacy_drops(mod, legacy):
    assert mod.drops() == legacy.partsdb.drops()
    assert len(mod.drops()["drops"]) > 0


def test_matches_legacy_drops_by_item(mod, legacy):
    theirs = legacy.partsdb.drops_by_item()
    assert dict(mod.drops_by_item()) == theirs
    assert len(theirs) > 0
    assert all(isinstance(v, list) and v for v in mod.drops_by_item().values())


def test_matches_legacy_part_meta_for_every_ref(mod, legacy, all_refs):
    """Every (category, index) with a parts-table row, every key in part_meta.json, and refs that
    do not exist."""
    meta_keys = [tuple(int(x) for x in k.split(":")) for k in legacy.partsdb.part_meta()]
    refs = set(all_refs) | set(meta_keys) | {(None, 1), (1, None), (999999, 1), (21, 999999), ("x", "y")}
    assert len(refs) > 1000
    for cat, idx in refs:
        assert mod.part_meta(cat, idx) == legacy.partsdb.meta_for(cat, idx), (cat, idx)
    assert sum(1 for c, i in refs if mod.part_meta(c, i)) == len(legacy.partsdb.part_meta())


PRETTY_EDGE_NAMES = [
    "", "x", " part_x ", "part_", "PART_UPPER_case", "ABC def", "a__b", "part_scope_02_lens_02",
    "comp_05_legendary", "comp_05_legendary_04", "comp_05_legendary_hellwalker", "comp_05_Legendary_X",
    "comp_06_pearl_x_y", "comp_09_weird_thing", "comp_00_zero_thing", "comp_5_legendary_kaos",
    "comp_01_common", "comp_07_vile_thing", "comp_05_legendary_Two_Words",
]


def test_matches_legacy_prettify_part_every_part_name(mod, legacy, category_ids):
    names = {raw for c in category_ids for raw in legacy.partsdb.part_table(c).values()}
    assert len(names) > 1000
    for raw in sorted(names) + PRETTY_EDGE_NAMES:
        assert mod.prettify_part(raw) == legacy.partsdb.prettify_part(raw), raw


def test_matches_legacy_prettify_legendary_every_suffix(mod, legacy, category_ids):
    import re
    suffixes = set()
    for c in category_ids:
        for raw in legacy.partsdb.part_table(c).values():
            m = re.match(r"^comp_(\d+)_([a-z]+)(?:_(.+))?$", raw)
            if m and m.group(3):
                suffixes.add(m.group(3))
    suffixes |= set(legacy.partsdb.item_names())               # every key of the name table
    suffixes |= {k[3:] for k in legacy.partsdb.item_names() if k.startswith("np_")}
    suffixes |= {"", None, "  ", "04", " 04 ", "0", "hellwalker", "HELLWALKER", "  Hellwalker ", "np_x",
                 "two_words", "UPPER_case", "x" * 40}
    assert len(suffixes) > 500
    for s in suffixes:
        assert mod.prettify_legendary(s) == legacy.partsdb.prettify_legendary(s), repr(s)


def test_matches_legacy_is_weapon_category(mod, legacy, category_ids):
    flags = {}
    for cid in category_ids + EXTRA_CATEGORY_IDS:
        flags[cid] = mod.is_weapon_category(cid)
        assert flags[cid] == legacy.partsdb.is_weapon_category(cid), cid
    assert any(flags.values()) and not all(flags.values())     # it discriminates
    assert flags[None] is False


def test_matches_legacy_across_the_serial_database(mod, legacy, serial_refs):
    """Run against everything the 9,875 community serials actually reference."""
    refs, cats = serial_refs
    assert len(refs) > 1000 and len(cats) > 20
    for cat, idx, raw in refs:
        assert mod.part_table(cat).get(idx) == raw, (cat, idx)
        assert mod.part_meta(cat, idx) == legacy.partsdb.meta_for(cat, idx), (cat, idx)
        if raw:
            assert mod.prettify_part(raw) == legacy.partsdb.prettify_part(raw), raw
    for cat in cats:
        assert mod.category_names().get(cat) == legacy.partsdb.category_names().get(cat), cat
        assert mod.is_weapon_category(cat) == legacy.partsdb.is_weapon_category(cat), cat
