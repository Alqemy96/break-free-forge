"""builder module: one test per CONTRACT.md invariant, parity with the legacy `cmd_build` resolution
loop (legacy `search` + `enrich`), and an end-to-end check with the real render module.

The legacy scripts are the oracle (never modified). Neighbours are the REAL catalog and ops (and
everything under them); forced-failure tests swap in thin wrappers around the real instances via
`Forge.build(overrides=...)`.
"""
from __future__ import annotations

import dataclasses
import html as html_lib
import json

import pytest

from bl4forge.core import vocab
from bl4forge.core.config import Config
from bl4forge.core.errors import SerialError, UndeclaredDependency
from bl4forge.core.forge import Forge
from bl4forge.core.module import ModuleContext, conformance_problems
from bl4forge.core.ports import BuilderPort
from bl4forge.core.types import (
    CatalogEntry, HealthReport, Loadout, LoadoutItem, LoadoutRequest, SearchQuery, SearchResult,
)
from bl4forge.modules.builder import MODULE, BuilderModule, describe_request

KNOWN_SERIAL = r"@Uge(J0Fme!K{9I5@RG/*Fs6^dF^+SzB{X<<U4k{EX7U~sh7HS*<"       # 'anarchy' shotgun, stored level 50
KNOWN_SERIAL_60 = r"@Uge(J0FnkbU{9I5@RG/*Fs6^dF^+SzB{X<<U4k{EX7U~sh7HS*<"   # the same item at level 60


# ---------------------------------------------------------------------------------------------
# fixtures and helpers
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mesh(config, legacy):
    legacy.partsdb.set_owned_packs(config.owned_packs)      # legacy's owned set is process-global
    return Forge.build(config)


@pytest.fixture(scope="module")
def builder(mesh):
    return mesh.builder


class Delegate:
    """A stand-in for a real module instance that overrides single methods and forwards the rest."""

    def __init__(self, real, **overrides):
        self._real = real
        self.__dict__.update(overrides)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _boom(*_a, **_k):
    raise SerialError("forced failure")


def reqs(spec):
    return [LoadoutRequest.from_dict(d) for d in spec]


def module_with(config, catalog, ops):
    return BuilderModule(ModuleContext("builder", config, {"catalog": catalog, "ops": ops}))


class SpyCatalog:
    """Counts searches; returns a canned SearchResult (or raises)."""

    def __init__(self, result=None, error=None):
        self.result, self.error, self.queries = result or SearchResult(), error, []

    def search(self, query):
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.result


# ---------------------------------------------------------------------------------------------
# the legacy oracle: the request-resolution loop of `cmd_build`, in process
# ---------------------------------------------------------------------------------------------

def legacy_resolve(legacy, spec, level):
    """forge.py `cmd_build` lines 631-690 without the file output: (items, groups, missing)."""
    F = legacy.forge
    items, groups, missing = [], [], []
    for req in spec:
        group = req.get("group")
        if group and group not in groups:
            groups.append(group)
        note = req.get("note", "")
        display = req.get("label_name") or req.get("display_name")
        if req.get("serial"):
            entry = {
                "itemName": req.get("name", "Item"),
                "manufacturer": req.get("manufacturer", ""),
                "manufacturerWeaponType": req.get("label", ""),
                "type": req.get("type", ""), "weaponType": req.get("weaponType", ""),
                "rarity": req.get("rarity", ""), "bulletType": req.get("element", "N/A"),
                "source": "", "serial": req["serial"],
            }
            it = F.enrich(entry, level)
            it["note"], it["group"] = note, group
            if display:
                it["display_name"] = display
            items.append(it)
        else:
            count = int(req.get("count", 1))
            res = F.search(query=req.get("query"), type_=req.get("type"),
                           element=req.get("element"), manufacturer=req.get("manufacturer"),
                           rarity=req.get("rarity"), character=req.get("character"), limit=count)
            if not res:
                missing.append(req.get("query") or json.dumps(req))
                continue
            for e in res:
                it = F.enrich(e, level)
                it["note"], it["group"] = note, group
                if display:
                    it["display_name"] = display
                items.append(it)
    return items, groups, missing


def legacy_element(it):
    """The element legacy SHOWED: the decoded one, else the database label ('electric' -> 'shock')."""
    if it.get("true_element"):
        return vocab.normalize_element(it["true_element"])
    label = it.get("element")
    return None if label in (None, "", "N/A") else vocab.normalize_element(label)


def assert_item_matches_legacy(new: LoadoutItem, old: dict):
    assert new.serial == old["serial"]
    assert new.level == old["level"]
    assert new.rarity == (old.get("true_rarity") or old["rarity"])
    assert new.element == legacy_element(old)
    assert new.name == old["name"]
    assert new.legendary_name == old.get("legendary_name")
    assert new.category == old.get("category")
    assert new.parts == tuple(old.get("parts", ()))
    assert new.odds == old.get("odds", "")
    assert list(new.warnings) == old["warnings"]
    assert (new.manufacturer, new.label, new.type, new.weapon_type, new.source) == (
        old["manufacturer"], old["label"], old["type"], old["weaponType"], old["source"])
    assert (new.group, new.note, new.display_name) == (old["group"], old["note"], old.get("display_name"))


def assert_build_matches_legacy(legacy, builder, spec, level, title="Parity"):
    old_items, old_groups, old_missing = legacy_resolve(legacy, spec, level)
    lo = builder.build(reqs(spec), level=level, title=title)
    assert [i.serial for i in lo.items] == [o["serial"] for o in old_items]       # order
    assert lo.groups == tuple(old_groups)
    # a miss is named by its query, exactly as legacy did; legacy's json.dumps(req) becomes the compact
    # description (the one deliberate difference, see CONTRACT.md)
    assert len(lo.unmatched) == len(old_missing)
    for mine, theirs in zip(lo.unmatched, old_missing):
        assert mine == (describe_request(LoadoutRequest.from_dict(json.loads(theirs)))
                        if theirs.startswith("{") else theirs)
    for new, old in zip(lo.items, old_items):
        assert_item_matches_legacy(new, old)
    assert (lo.title, lo.level) == (title, level)
    return lo, old_items


def first_serial(legacy, **flags):
    return legacy.forge.search(limit=1, **flags)[0]["serial"]


# The three example loadouts from legacy/README.md ("How to use it"), as spec entries.
README_CRYO = [
    {"group": "Weapons", "type": "shotgun", "element": "cryo", "note": "Cryo <em>shotgun</em>"},
    {"group": "Weapons", "type": "smg", "element": "cryo"},
    {"group": "Weapons", "type": "pistol", "element": "cryo"},
    {"group": "Weapons", "type": "sniper", "element": "cryo"},
    {"group": "Gear", "type": "shield", "element": "cryo"},
    {"group": "Gear", "type": "classmod", "character": "gravitar"},
    {"group": "Gear", "type": "grenade", "element": "cryo"},
    {"group": "Gear", "type": "repkit"},
]
README_COMBO = [
    {"group": "Weapons", "query": "wombo combo", "element": "cryo", "display_name": "Wombo Combo",
     "note": "The <em>combo</em> gun"},
    {"group": "Weapons", "query": "plasma coil", "display_name": "Plasma Coil"},
    {"group": "Gear", "query": "super soldier", "element": "cryo", "type": "shield",
     "display_name": "Super Soldier"},
]
README_RADIATION_SHOTGUN = [{"type": "shotgun", "element": "radiation"}]

OTHER_SPECS = {
    "classmod_gravitar": [{"group": "Gear", "type": "classmod", "character": "gravitar", "count": 2}],
    "classmod_dark_siren": [{"group": "Gear", "type": "classmod", "character": "dark siren"}],
    "classmod_exo_soldier": [{"type": "classmod", "character": "exo_soldier", "rarity": "legendary"}],
    "classmod_paladin": [{"type": "com", "character": "Paladin"}],
    "shield": [{"group": "Gear", "type": "shield", "manufacturer": "maliwan", "element": "shock"}],
    "repkit": [{"group": "Gear", "type": "repkit", "count": 2, "note": "heals"}],
    "grenade": [{"group": "Gear", "type": "grenade", "element": "corrosive"}],
    "enhancement": [{"group": "Gear", "type": "enhancement", "manufacturer": "maliwan"}],
    "assault_rifle": [{"type": "ar", "element": "electric", "limit": 1}],
    "heavy_and_pistol": [{"group": "A", "type": "heavy", "element": "fire"},
                         {"group": "B", "type": "ps", "element": "impact"}],
    "count_three": [{"group": "Variants", "type": "smg", "element": "corrosive", "count": 3,
                     "note": "pick one", "display_name": "SMG option"}],
    "named_query": [{"query": "anarchy", "type": "shotgun", "count": 4}],
    "misses_and_hits": [{"group": "Weapons", "query": "zz no such item zz"},
                        {"group": "Weapons", "type": "shotgun", "element": "plasma"},
                        {"group": "Weapons", "type": "sg", "element": "fire"}],
    "groups_interleaved": [{"group": "B", "type": "shield"}, {"group": "A", "type": "repkit"},
                           {"group": "B", "type": "grenade"}, {"type": "enhancement"}],
}


# ---------------------------------------------------------------------------------------------
# port conformance and module wiring
# ---------------------------------------------------------------------------------------------

def test_module_declares_its_cell(builder):
    assert MODULE is BuilderModule
    assert (BuilderModule.name, BuilderModule.requires, BuilderModule.port) == (
        "builder", ("catalog", "ops"), BuilderPort)
    assert BuilderModule.purpose == "Turn loadout requests into a verified, re-leveled Loadout."
    assert conformance_problems(builder, BuilderPort) == []


def test_sees_only_declared_neighbours(builder):
    assert builder.dep("catalog") is not None and builder.dep("ops") is not None
    for other in ("codec", "data", "rules", "render"):
        with pytest.raises(UndeclaredDependency):
            builder.dep(other)


def test_health_is_a_real_known_answer_check(builder, mesh):
    rep = builder.health()
    assert isinstance(rep, HealthReport) and rep.ok, rep
    assert {c.name for c in rep.checks} >= {"one_item_at_60", "explicit_serial", "miss_is_unmatched"}
    assert mesh.states["builder"].state == "ok"


def test_health_fails_honestly_and_never_raises(config, mesh):
    for broken in (Delegate(mesh.ops, relevel=_boom), Delegate(mesh.ops, describe=_boom)):
        rep = module_with(config, mesh.catalog, broken).health()
        assert isinstance(rep, HealthReport) and not rep.ok
    rep = module_with(config, SpyCatalog(error=RuntimeError("db gone")), mesh.ops).health()
    assert not rep.ok and any(not c.ok for c in rep.checks)
    rep = module_with(config, object(), object()).health()          # neighbours that answer nothing
    assert not rep.ok


# ---------------------------------------------------------------------------------------------
# CONTRACT invariants, each under its own name
# ---------------------------------------------------------------------------------------------

def test_relevel_failure_is_a_warning(config, mesh):
    """A codec whose relevel raises: the item is NOT presented as re-leveled (real stored level,
    original code) and says so. Both when ops is built on that codec and when ops itself fails."""
    sick_codec = Delegate(mesh.codec, relevel=_boom)
    chain = Forge.build(config, overrides={"codec": sick_codec})
    assert chain.states["builder"].state == "degraded"         # its own health notices
    for builder, label in ((chain.builder, "codec fails"),
                           (module_with(config, mesh.catalog, Delegate(mesh.ops, relevel=_boom)), "ops fails")):
        lo = builder.build(reqs([{"type": "shotgun", "element": "cryo", "count": 2},
                                 {"serial": KNOWN_SERIAL}]), level=60)
        assert len(lo.items) == 3, label
        for item in lo.items:
            assert item.level != 60, label                      # not claimed as re-leveled
            assert any(w.startswith("re-level to 60 failed") and "forced failure" in w
                       for w in item.warnings), (label, item.warnings)
            assert any("requested level 60 but the code decodes as" in w for w in item.warnings)
        assert lo.items[-1].serial == KNOWN_SERIAL and lo.items[-1].level == 50
    # without a requested level nothing is re-leveled, so nothing can fail
    assert not chain.builder.build(reqs([{"serial": KNOWN_SERIAL}])).items[0].warnings


def test_relevel_that_returns_garbage_is_a_warning(config, mesh):
    for bad in (None, "", 60):
        b = module_with(config, mesh.catalog, Delegate(mesh.ops, relevel=lambda s, lv, bad=bad: bad))
        item = b.build(reqs([{"serial": KNOWN_SERIAL}]), level=60).items[0]
        assert item.serial == KNOWN_SERIAL and item.level == 50
        assert any(w.startswith("re-level to 60 failed") for w in item.warnings)


def test_level_mismatch_is_a_warning(config, mesh):
    """ops claims success but hands back the unchanged code (level 50): requested != decoded."""
    b = module_with(config, mesh.catalog, Delegate(mesh.ops, relevel=lambda serial, level: serial))
    item = b.build(reqs([{"serial": KNOWN_SERIAL}]), level=60).items[0]
    assert item.level == 50
    assert "requested level 60 but the code decodes as 50" in item.warnings
    assert not any(w.startswith("re-level") for w in item.warnings)      # no exception, only a mismatch


def test_a_level_that_takes_has_no_warning(builder):
    lo = builder.build(reqs([{"serial": KNOWN_SERIAL}]), level=60)
    item = lo.items[0]
    assert (item.serial, item.level, item.warnings) == (KNOWN_SERIAL_60, 60, ())


def test_misses_are_unmatched(builder):
    spec = [{"group": "G", "query": "zz no such item zz"},
            {"type": "shotgun", "element": "plasma"},                 # an element nobody knows
            {"type": "shotgun", "element": "cryo", "manufacturer": "no-such-maker"},
            {"type": "no-such-type", "rarity": "common"},
            {"group": "G", "type": "shield"}]
    lo = builder.build(reqs(spec), level=60)                          # nothing raises
    assert lo.unmatched == ("zz no such item zz", "type=shotgun element=plasma",
                            "type=shotgun element=cryo manufacturer=no-such-maker",
                            "type=no-such-type rarity=common")
    assert len(lo.items) == 1 and lo.items[0].group == "G"
    assert lo.groups == ("G",)                      # a group is kept even when one of its requests missed
    empty = builder.build([], level=60)
    assert empty == Loadout(title="Break Free Loadout", level=60)
    only_miss = builder.build(reqs([{"query": "zz no such item zz"}]))
    assert only_miss.items == () and only_miss.unmatched == ("zz no such item zz",)


def test_groups_keep_first_seen_order(builder):
    spec = OTHER_SPECS["groups_interleaved"] + [{"group": "C", "type": "shield"}, {"group": "A", "type": "sg"}]
    lo = builder.build(reqs(spec), level=60)
    assert lo.groups == ("B", "A", "C")
    assert [i.group for i in lo.items] == ["B", "A", "B", None, "C", "A"]
    # the items follow the request order, not the group order
    assert [i.type for i in lo.items][:4] == ["shield", "repair_kit", "gadget", "enhancement"]


def test_count_gt_1_returns_variants(builder):
    lo = builder.build(reqs([{"group": "V", "type": "smg", "element": "corrosive", "count": 3,
                              "note": "pick one", "display_name": "Option"}]), level=60)
    assert len(lo.items) == 3
    assert len({i.serial for i in lo.items}) == 3                     # distinct variants
    assert {(i.group, i.note, i.display_name, i.level, i.element) for i in lo.items} == {
        ("V", "pick one", "Option", 60, "corrosive")}
    single = builder.build(reqs([{"type": "smg", "element": "corrosive"}]), level=60)
    assert single.items[0].serial == lo.items[0].serial               # count only widens the same search
    short = builder.build(reqs([{"query": "wombo combo", "element": "cryo", "count": 50}]), level=60)
    assert 1 <= len(short.items) < 50
    assert any("asked for 50, found %d" % len(short.items) in w for w in short.warnings)


def test_explicit_serial_entries_work(config, mesh):
    spy = SpyCatalog(error=AssertionError("an explicit serial must not be searched"))
    b = module_with(config, spy, mesh.ops)
    spec = [{"group": "Gear", "serial": KNOWN_SERIAL, "display_name": "My Gun", "label": "Tediore Shotgun",
             "element": "impact", "note": "mine <em>only</em>", "name": "Hand-picked", "type": "weapon"},
            {"serial": '  "%s",  ' % KNOWN_SERIAL}]               # pasted from JSON: quotes + comma
    lo = b.build(reqs(spec), level=60)
    assert spy.queries == []                                       # search skipped
    first, pasted = lo.items
    assert (first.serial, first.level, first.warnings) == (KNOWN_SERIAL_60, 60, ())
    assert (first.group, first.display_name, first.shown_name, first.note) == (
        "Gear", "My Gun", "My Gun", "mine <em>only</em>")
    assert (first.name, first.label, first.type) == ("Hand-picked", "Tediore Shotgun", "weapon")
    assert (first.legendary_name, first.rarity, first.element, first.category) == (
        "Anarchy", "Legendary", "impact", "Tediore Shotgun")
    assert first.parts and first.odds
    assert pasted.serial == KNOWN_SERIAL_60 and pasted.name == "Item" and pasted.shown_name == "Anarchy"
    assert lo.unmatched == () and lo.warnings == ()


def test_explicit_serial_that_cannot_be_decoded_is_a_warning(builder):
    lo = builder.build(reqs([{"serial": "not-a-serial", "name": "Junk"}]), level=60)
    (item,) = lo.items                                              # still listed, never raised
    assert item.serial == "not-a-serial" and item.level is None and item.name == "Junk"
    assert any(w.startswith("re-level to 60 failed") for w in item.warnings)
    assert any(w.startswith("decode failed:") for w in item.warnings)
    assert item.rarity == "" and item.parts == () and item.odds == ""


def test_decoded_facts_override_catalog_hints(builder):
    """The database says Cryo / Rare / 'Some Name'; the serial is a Legendary 'Anarchy' with no element part."""
    lying = CatalogEntry(serial=KNOWN_SERIAL, name="Some Name", type="weapon", weapon_type="shotgun",
                         manufacturer="Tediore", label="Tediore Shotgun", rarity="Rare", element="cryo",
                         source="GunCodes_x.txt")
    item = builder.enrich(lying, 60)
    assert (item.rarity, item.element, item.legendary_name, item.category) == (
        "Legendary", "impact", "Anarchy", "Tediore Shotgun")
    assert item.name == "Some Name"                               # the hint is kept as `name`...
    assert item.shown_name == "Anarchy"                           # ...but the decoded name is what shows
    assert "database says element Cryo, the serial says Impact — trusting the serial" in item.warnings
    assert "database says rarity Rare, the serial says Legendary — trusting the serial" in item.warnings
    # agreement is silent; a missing hint is silent too (and gets filled in)
    ok = builder.enrich(dataclasses.replace(lying, rarity="legendary", element="impact"), 60)
    blank = builder.enrich(dataclasses.replace(lying, rarity="", element=None), 60)
    assert ok.warnings == () and blank.warnings == ()
    assert (blank.rarity, blank.element) == ("Legendary", "impact")


def test_hints_stand_when_nothing_is_decoded(builder):
    """Gear has no element in the bitstream, so a shield keeps its catalog element; a weapon never does."""
    shield = builder.build(reqs([{"type": "shield", "element": "cryo"}]), level=60).items[0]
    assert shield.element == "cryo" and shield.warnings == ()
    bad = CatalogEntry(serial=KNOWN_SERIAL, name="x", rarity="Legendary", element="plasma")
    item = builder.enrich(bad, 60)
    assert item.element == "impact"                               # decoded wins over a nonsense hint
    assert any("plasma" in w and "ignored" in w for w in item.warnings)
    gear = builder.build(reqs([{"serial": first_serial_in(builder, "shield"), "element": "plasma"}]), level=60)
    assert gear.items[0].element is None
    assert any("plasma" in w and "ignored" in w for w in gear.items[0].warnings)


def first_serial_in(builder, type_):
    return builder.dep("catalog").search(SearchQuery(type=type_, limit=1)).entries[0].serial


def test_item_element_is_a_vocab_name_or_none(builder):
    spec = README_CRYO + README_COMBO + [{"type": t, "count": 3} for t in
                                         ("ar", "sg", "ps", "smg", "sniper", "heavy", "shield", "classmod",
                                          "repkit", "grenade", "enhancement")]
    lo = builder.build(reqs(spec), level=60)
    assert len(lo.items) > 30
    for item in lo.items:
        assert item.element is None or item.element in vocab.ELEMENTS, item
        if item.type == "weapon":
            assert item.element in vocab.ELEMENTS                 # a decoded weapon always has one
        if item.type in ("classmod", "repair_kit", "enhancement"):
            assert item.element is None


def test_level_none_means_do_not_relevel(builder):
    lo = builder.build(reqs([{"serial": KNOWN_SERIAL}, {"query": "anarchy", "type": "shotgun"}]))
    assert lo.level is None
    assert [i.serial for i in lo.items][0] == KNOWN_SERIAL
    assert all(i.level == 50 and i.warnings == () for i in lo.items)
    again = builder.build(reqs([{"serial": KNOWN_SERIAL}]), level=45)
    assert again.items[0].level == 45 and again.level == 45
    assert builder.build(reqs([{"serial": KNOWN_SERIAL}]), level="55").items[0].level == 55


def test_a_level_that_is_not_a_number_is_reported(builder):
    lo = builder.build(reqs([{"serial": KNOWN_SERIAL}]), level="sixty")
    assert lo.level is None and lo.items[0].level == 50
    assert any("not a whole number" in w for w in lo.warnings)
    item = builder.enrich(CatalogEntry(serial=KNOWN_SERIAL, name="x"), "sixty")      # port-level call
    assert item.level == 50 and any(w.startswith("re-level to sixty failed") for w in item.warnings)


# ---------------------------------------------------------------------------------------------
# reporting of filtered / odd requests (nothing is silently lost)
# ---------------------------------------------------------------------------------------------

def test_hidden_and_short_results_are_reported(config, mesh):
    row = mesh.catalog.find_by_serial(KNOWN_SERIAL)
    canned = SearchResult(entries=(row,), hidden_by_pack={"bounty_pack_3": 2, "story_pack_1": 1},
                          dropped_element_mismatch=4)
    spy = SpyCatalog(canned)
    lo = module_with(config, spy, mesh.ops).build(reqs([{"query": "frangible", "count": 3}]), level=60)
    assert len(lo.items) == 1
    assert any("frangible" in w and "bounty_pack_3: 2" in w and "story_pack_1: 1" in w and "not owned" in w
               for w in lo.warnings)
    assert any("4 catalog label(s) disagreed" in w for w in lo.warnings)
    assert any("asked for 3, found 1" in w for w in lo.warnings)
    q = spy.queries[0]
    assert (q.query, q.limit, q.verify_element, q.include_unowned) == ("frangible", 3, True, False)
    # nothing left at all: the miss is unmatched AND the reason is reported
    spy2 = SpyCatalog(SearchResult(hidden_by_pack={"bounty_pack_3": 5}))
    lo2 = module_with(config, spy2, mesh.ops).build(reqs([{"query": "frangible"}]), level=60)
    assert lo2.unmatched == ("frangible",) and lo2.items == ()
    assert any("bounty_pack_3: 5" in w for w in lo2.warnings)


def test_unowned_content_is_hidden_and_reported_for_real(config):
    cfg = dataclasses.replace(config, owned_packs=tuple(p for p in config.owned_packs if p != "bounty_pack_3"))
    poor = Forge.build(cfg).builder
    lo = poor.build(reqs([{"query": "frangible", "count": 25}]), level=60)
    assert lo.items and all(i.warnings == () for i in lo.items)
    assert any("bounty_pack_3" in w and "not owned" in w for w in lo.warnings)


def test_a_failing_search_is_reported_not_raised(config, mesh):
    b = module_with(config, SpyCatalog(error=RuntimeError("database is gone")), mesh.ops)
    lo = b.build(reqs([{"query": "anarchy"}, {"serial": KNOWN_SERIAL}]), level=60)
    assert lo.unmatched == ("anarchy",)
    assert any("anarchy" in w and "RuntimeError" in w and "database is gone" in w for w in lo.warnings)
    assert len(lo.items) == 1                                          # the explicit serial still builds


def test_empty_and_odd_requests_are_reported(builder):
    lo = builder.build(reqs([{}, {"group": "G", "note": "nothing to search for"},
                             {"type": "shield", "count": 0}, {"type": "shield", "count": -2}]), level=60)
    assert lo.unmatched == ("(empty request)", "(empty request)")
    assert len(lo.items) == 2 and lo.groups == ("G",)                  # count < 1 -> asks for one
    assert sum("count" in w and "asking for 1" in w for w in lo.warnings) == 2
    assert sum("neither a serial nor any search field" in w for w in lo.warnings) == 2
    assert builder.build([{"type": "shield"}], level=60).items               # plain dicts are tolerated


def test_unmatched_text_is_the_query_else_a_compact_description():
    assert describe_request(LoadoutRequest(query="wombo combo", type="smg")) == "wombo combo"
    assert describe_request(LoadoutRequest(type="shotgun", element="cryo", character="paladin")) == (
        "type=shotgun element=cryo character=paladin")
    assert describe_request(LoadoutRequest(group="G", note="n", count=3)) == "(empty request)"


# ---------------------------------------------------------------------------------------------
# matches_legacy: parity with legacy `cmd_build`'s resolution loop
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("level", [60, None])
@pytest.mark.parametrize("name,spec", [("readme_cryo_loadout", README_CRYO),
                                       ("readme_wombo_plasma_super_soldier", README_COMBO),
                                       ("readme_radiation_shotgun", README_RADIATION_SHOTGUN)])
def test_matches_legacy_readme_examples(legacy, builder, name, spec, level):
    lo, old = assert_build_matches_legacy(legacy, builder, spec, level, title=name)
    assert len(lo.items) >= len(spec)                                  # every example resolved
    assert lo.unmatched == ()
    if level == 60:
        assert {i.level for i in lo.items} == {60} and all(i.warnings == () for i in lo.items)


@pytest.mark.parametrize("level", [60, None])
@pytest.mark.parametrize("name", sorted(OTHER_SPECS))
def test_matches_legacy_other_specs(legacy, builder, name, level):
    spec = [{k: v for k, v in r.items() if k != "limit"} for r in OTHER_SPECS[name]]
    lo, old = assert_build_matches_legacy(legacy, builder, spec, level, title=name)
    if name != "misses_and_hits":
        assert lo.unmatched == ()
    else:
        assert lo.unmatched == ("zz no such item zz", "type=shotgun element=plasma")   # legacy: json.dumps(req)
        assert len(old) == len(lo.items) > 0


def test_matches_legacy_explicit_serial_request(legacy, builder):
    shield = first_serial(legacy, type_="shield", element="cryo")
    spec = [{"group": "Gear", "serial": shield, "display_name": "Super Soldier", "label": "Daedalus Shield",
             "element": "cryo", "note": "explicit <em>entry</em>", "name": "Chosen", "manufacturer": "Daedalus",
             "type": "shield", "rarity": "Legendary"},
            {"group": "Weapons", "serial": KNOWN_SERIAL},
            {"group": "Gear", "type": "repkit", "serial": first_serial(legacy, type_="repkit")}]
    for level in (60, None, 30):
        lo, old = assert_build_matches_legacy(legacy, builder, spec, level)
        assert [i.group for i in lo.items] == ["Gear", "Weapons", "Gear"]
        assert lo.items[0].element == "cryo" and lo.items[0].shown_name == "Super Soldier"


def test_matches_legacy_the_whole_database(legacy, builder, mesh):
    """`enrich` on every distinct serial's first row, re-leveled to 60: identical to legacy `enrich`."""
    first_row = {}
    for row in legacy.forge.load_db():
        first_row.setdefault(row["serial"], row)
    assert len(first_row) == 8520
    for serial, row in first_row.items():
        entry = mesh.catalog.find_by_serial(serial)
        assert entry is not None and entry.serial == serial
        assert_item_matches_legacy(
            dataclasses.replace(builder.enrich(entry, 60), group=None, note="", display_name=None),
            dict(legacy.forge.enrich(row, 60), group=None, note=""))


def test_matches_legacy_when_the_database_lies(legacy, builder, mesh):
    """Rows whose element label the bitstream contradicts: same warning text, same winner (the serial)."""
    flagged = 0
    for serial, row in {r["serial"]: r for r in legacy.forge.load_db() if r.get("type") == "weapon"}.items():
        old = legacy.forge.enrich(row, 60)
        if not any(w.startswith("database says element") for w in old["warnings"]):
            continue
        flagged += 1
        new = builder.enrich(mesh.catalog.find_by_serial(serial), 60)
        assert [w for w in new.warnings if w.startswith("database says element")] == [
            w for w in old["warnings"] if w.startswith("database says element")]
        assert new.element == vocab.normalize_element(old["true_element"])
    assert flagged > 50                                              # ~3.3% of 2,459 weapons


# ---------------------------------------------------------------------------------------------
# with the REAL render module
# ---------------------------------------------------------------------------------------------

def test_render_shows_every_built_serial(mesh, builder):
    render = mesh.render
    spec = README_CRYO + README_COMBO + [
        {"group": "Weapons", "serial": KNOWN_SERIAL, "note": "x <script>alert(1)</script>"},
        {"group": "Weapons", "query": "zz no such item zz"}]
    lo = builder.build(reqs(spec), level=60, title="Cryohawk Loadout")
    assert len(lo.items) == len(README_CRYO) + len(README_COMBO) + 1 and lo.unmatched
    doc = render.html(lo)
    plain = render.text(lo)
    assert "Cryohawk Loadout" in doc
    for item in lo.items:
        assert html_lib.escape(item.serial, quote=True) in doc, item.serial
        assert item.serial in html_lib.unescape(doc)
        assert plain.splitlines().count(item.serial) == 1
        assert item.shown_name and html_lib.escape(item.shown_name, quote=True) in doc
    assert "<script>alert(1)</script>" not in doc                    # the render escapes the note
    assert "zz no such item zz" in doc                               # and shows what was not matched
    assert doc.count("Lv 60") >= len(lo.items)


def test_render_shows_the_warnings_of_a_failed_relevel(config, mesh):
    b = module_with(config, mesh.catalog, Delegate(mesh.ops, relevel=_boom))
    lo = b.build(reqs([{"serial": KNOWN_SERIAL}]), level=60)
    doc = mesh.render.html(lo)
    assert "re-level to 60 failed" in doc and html_lib.escape(KNOWN_SERIAL) in doc


def test_two_forges_do_not_interfere(config, mesh):
    other = Forge.build(config, overrides={"ops": Delegate(mesh.ops, relevel=_boom)})
    a = mesh.builder.build(reqs([{"serial": KNOWN_SERIAL}]), level=60).items[0]
    b = other.builder.build(reqs([{"serial": KNOWN_SERIAL}]), level=60).items[0]
    a2 = mesh.builder.build(reqs([{"serial": KNOWN_SERIAL}]), level=60).items[0]
    assert a.warnings == () == a2.warnings and b.warnings and a == a2


def test_synthetic_probe_constants_match_the_shipped_known_answers(config):
    """The builder's built-in probe for the demo set must equal data/synthetic/manifest/known_answers.json."""
    if not config.is_synthetic:
        pytest.skip("only meaningful on the bundled synthetic dataset")
    import json
    from bl4forge.modules.builder import _SYNTHETIC_KNOWN
    shipped = json.loads((config.manifest_dir / "known_answers.json").read_text(encoding="utf-8"))["builder"]
    assert {k: shipped[k] for k in _SYNTHETIC_KNOWN} == _SYNTHETIC_KNOWN
