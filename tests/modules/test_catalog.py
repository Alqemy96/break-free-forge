"""catalog module: parity with the legacy `forge.search` over the whole serial database, plus one
test per CONTRACT.md invariant. The legacy scripts are the oracle (never modified).

Neighbours: the default fixtures use the REAL codec and data and the legacy-backed RulesPort/OpsPort
doubles (tests/doubles.py), so this file is independent of the rules/ops modules. Their real
implementations are exercised by `test_with_real_neighbours` (skipped until both report 'ok').
"""
import contextlib
import dataclasses
import json
import sys
import time
from collections import Counter

import pytest

from bl4forge.core import vocab
from bl4forge.core.errors import DataMissing, SerialError
from bl4forge.core.forge import Forge
from bl4forge.core.module import ModuleContext, conformance_problems
from bl4forge.core.ports import CatalogPort
from bl4forge.core.types import CatalogEntry, ItemInfo, SearchQuery, SearchResult
from bl4forge.modules.catalog import MODULE, CatalogModule
from bl4forge.modules.catalog import _db, _match
from tests.doubles import build_forge

BIG = 10 ** 6          # "no limit" for legacy search (it breaks when len(out) >= limit)
KNOWN_SERIAL = "@Uge(J0Fme!K{9I5@RG/*Fs6^dF^+SzB{X<<U4k{EX7U~sh7HS*<"   # first 'anarchy' shotgun row


# ---------------------------------------------------------------------------------------------
# helpers: legacy oracle + comparison
# ---------------------------------------------------------------------------------------------

def _query(flags):
    """Legacy `search` keyword arguments -> SearchQuery (`type_` is `type`; `_mine` overrides)."""
    f = {k: v for k, v in flags.items() if k != "_mine"}
    if "type_" in f:
        f["type"] = f.pop("type_")
    f.update(flags.get("_mine", {}))
    return SearchQuery(**f)


def _legacy(legacy, flags):
    """(result rows, last_skipped) from the real legacy search."""
    kw = {k: v for k, v in flags.items() if k != "_mine"}
    rows = legacy.forge.search(**kw)
    return rows, dict(legacy.forge.search.last_skipped)


def _legacy_element_drops(legacy, flags):
    """How many ROWS legacy drops at its element check, counted with legacy's own predicates.

    Re-runs the loop of legacy `search` (same order: match, element check, de-dup, ownership, limit)
    and returns (serials, dropped_rows, skipped). The first value is asserted equal to the real
    `search` result by the caller, so this replica cannot drift from the oracle unnoticed.
    """
    F = legacy.forge
    kw = {k: v for k, v in flags.items() if k != "_mine"}
    element, verify = kw.get("element"), kw.get("verify_element", True)
    limit = kw.get("limit", 25)
    seen, out, skipped, dropped = set(), [], {}, 0
    for e in F.load_db():
        if not F._matches(e, kw.get("query"), kw.get("type_"), element, kw.get("manufacturer"),
                          kw.get("rarity"), kw.get("character")):
            continue
        if element and verify and not F._element_ok(e, element):
            dropped += 1
            continue
        if e["serial"] in seen:
            continue
        seen.add(e["serial"])
        if not kw.get("include_unowned", False):
            ok, pack = F._ownership_ok(e["serial"])
            if not ok:
                skipped[pack] = skipped.get(pack, 0) + 1
                continue
        out.append(e["serial"])
        if len(out) >= limit:
            break
    return out, dropped, skipped


def _db_element(label):
    return None if label == "N/A" else vocab.normalize_element(label)


def _assert_entry_is_row(entry, row):
    assert isinstance(entry, CatalogEntry)
    assert (entry.serial, entry.name, entry.type, entry.weapon_type, entry.manufacturer,
            entry.rarity, entry.source) == (row["serial"], row["itemName"], row["type"],
                                            row["weaponType"], row["manufacturer"], row["rarity"],
                                            row["source"])
    assert entry.label == (row["manufacturerWeaponType"] or row["type"])
    assert entry.element == _db_element(row["bulletType"])


def _assert_parity(catalog, legacy, flags, exact_pack_keys=True):
    """One query: catalog.search == legacy search (rows, order, entries, hidden, dropped)."""
    rows, last_skipped = _legacy(legacy, flags)
    where = "query %r" % (flags,)
    if flags.get("element") and flags.get("verify_element", True):
        trace_serials, trace_dropped, trace_skipped = _legacy_element_drops(legacy, flags)
        assert trace_serials == [r["serial"] for r in rows], "replica of legacy diverged: " + where
        assert trace_skipped == last_skipped, "replica of legacy diverged: " + where
    else:
        trace_dropped = 0                 # the element check never runs: nothing can be dropped

    res = catalog.search(_query(flags))
    assert isinstance(res, SearchResult)
    assert [e.serial for e in res.entries] == [r["serial"] for r in rows], where
    for entry, row in zip(res.entries, rows):
        _assert_entry_is_row(entry, row)
    assert res.dropped_element_mismatch == trace_dropped, where
    assert sum(res.hidden_by_pack.values()) == sum(last_skipped.values()), where
    if exact_pack_keys:       # keys are pack ids; legacy keys them by label
        labels = legacy.partsdb.CONTENT_PACKS
        assert {labels.get(k, k): v for k, v in res.hidden_by_pack.items()} == last_skipped, where
    return res, rows


# ---------------------------------------------------------------------------------------------
# the battery
# ---------------------------------------------------------------------------------------------

def _battery():
    q = []
    weapons = ("pistol", "shotgun", "smg", "ar", "sniper", "heavy")
    elements = ("cryo", "fire", "radiation", "electric", "corrosive", "impact")
    # every weapon type x every element (the legacy alias 'electric' for the db's 'electric')
    for t in weapons:
        for el in elements:
            q.append(dict(type_=t, element=el, limit=10))
    # the same through the vocab spelling on our side only
    for t in ("pistol", "ar"):
        q.append(dict(type_=t, element="electric", limit=10, _mine={"element": "shock"}))
    # limits 1 / 5 / 25 / 100
    for lim in (1, 5, 25, 100):
        for el in ("cryo", "fire", "electric"):
            q.append(dict(type_="weapon", element=el, limit=lim))
        q.append(dict(limit=lim))
        q.append(dict(type_="shield", limit=lim))
        q.append(dict(query="anarchy", limit=lim))
    # gear types, and gear + element (shields/grenades carry a db element label; the bitstream has
    # none for gear, so the label is trusted - class mods and repkits are labelled N/A -> nothing)
    for t in ("shield", "repkit", "grenade", "classmod", "enhancement", "gadget", "repair_kit"):
        q.append(dict(type_=t, limit=100))
    q.append(dict(type_="shield", element="cryo", limit=25))
    q.append(dict(type_="classmod", element="fire", limit=25))
    # class mods per character (aliases for the same character included)
    for ch in ("gravitar", "dark_siren", "dark siren", "exo_soldier", "exo-soldier", "exo soldier",
               "paladin", "Gravitar", "siren"):
        q.append(dict(type_="classmod", character=ch, limit=25))
    q.append(dict(character="paladin", limit=100))
    q.append(dict(type_="class mod", character="dark_siren", rarity="legendary", limit=100))
    # name queries
    for name in ("anarchy", "wombo combo", "hellwalker", "plasma coil", "skeptic", "jelly", "kaoson",
                 "bod", "Anarchy", "zzz-no-such-item", "luty", "hot slugger", "super soldier"):
        q.append(dict(query=name, limit=25))
    q.append(dict(query="anarchy", element="cryo", limit=25))
    q.append(dict(query="anarchy", type_="shotgun", element="impact", limit=25))
    q.append(dict(query="wombo combo", type_="ar", element="fire", limit=25))
    q.append(dict(query="wombo combo", element="electric", limit=25))
    # rarity (a substring match, as in legacy: 'common' also matches 'Uncommon')
    for r in ("legendary", "epic", "rare", "uncommon", "common", "Legendary"):
        q.append(dict(rarity=r, limit=25))
    q.append(dict(rarity="epic", type_="smg", element="corrosive", limit=25))
    q.append(dict(rarity="legendary", type_="sniper", limit=100))
    # manufacturers (a substring match)
    for m in ("jakobs", "tediore", "torgue", "maliwan", "daedalus", "vladof", "order", "ripper",
              "hyperion", "cov", "atlas", "forgeknight", "Jakobs", "exo", "siren", "gravitar"):
        q.append(dict(manufacturer=m, limit=25))
    q.append(dict(manufacturer="maliwan", type_="smg", element="cryo", limit=25))
    q.append(dict(manufacturer="torgue", type_="heavy", element="fire", rarity="legendary", limit=100))
    q.append(dict(manufacturer="tediore", type_="shotgun", limit=100))
    # every type alias legacy knows, plus pass-through spellings
    for t in ("ar", "assault_rifle", "assaultrifle", "rifle", "repkit", "repair_kit", "repairkit",
              "classmod", "class_mod", "class mod", "com", "grenade", "ordnance", "gadget", "launcher",
              "rocket", "sr", "sniper", "smg", "sg", "shotgun", "ps", "pistol", "heavy", "shield",
              "enhancement", "weapon", "AR", "Repkit"):
        q.append(dict(type_=t, limit=25))
    # verify_element=False: labels trusted, nothing dropped
    for el in ("cryo", "fire", "radiation", "electric", "corrosive", "impact"):
        q.append(dict(element=el, limit=100, verify_element=False))
    q.append(dict(type_="ar", element="fire", limit=25, verify_element=False))
    # include_unowned=True
    for el in ("cryo", "fire", "electric"):
        q.append(dict(element=el, limit=100, include_unowned=True))
    q.append(dict(type_="smg", element="cryo", limit=100, include_unowned=True, verify_element=False))
    q.append(dict(limit=100, include_unowned=True))
    # full database, no cap: every element, verified and not
    for el in ("cryo", "fire", "radiation", "electric", "corrosive", "impact"):
        q.append(dict(element=el, limit=BIG))
        q.append(dict(element=el, limit=BIG, verify_element=False, include_unowned=True))
    return q


BATTERY = _battery()


# ---------------------------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def doubled(config, legacy):
    """Real codec/data/catalog on top of the legacy-backed rules and ops doubles."""
    legacy.partsdb.set_owned_packs(config.owned_packs)
    return build_forge(config, legacy, doubles=("rules", "ops"))


@pytest.fixture(scope="module")
def catalog(doubled):
    return doubled.catalog


@contextlib.contextmanager
def _restricted(config, legacy, drop=("bounty_pack_3",), real=False):
    """A forge whose player does NOT own `drop` (the shipped database has 26 serials in
    bounty_pack_3, none in story_pack_1). Legacy's owned set is process-global: always restore."""
    cfg = dataclasses.replace(config, owned_packs=tuple(p for p in config.owned_packs if p not in drop))
    try:
        if real:
            legacy.partsdb.set_owned_packs(cfg.owned_packs)
            yield cfg, Forge.build(cfg)
        else:
            yield cfg, build_forge(cfg, legacy, doubles=("rules", "ops"))
    finally:
        legacy.partsdb.set_owned_packs(config.owned_packs)


def _module(config, deps):
    return CatalogModule(ModuleContext("catalog", config, deps))


class StubData:
    def __init__(self, available=True):
        self._available = available

    def available(self):
        return self._available


class StubOps:
    """describe() answers from a table, or fails like a decoder on a malformed row."""
    def __init__(self, elements=None, fail=()):
        self.elements, self.fail = dict(elements or {}), set(fail)
        self.calls = 0

    def describe(self, serial):
        self.calls += 1
        if serial in self.fail:
            raise SerialError("cannot decode %s" % serial)
        return ItemInfo(serial=serial, element=self.elements.get(serial))


class StubRules:
    def __init__(self, unowned=None, fail=()):
        self.unowned, self.fail = dict(unowned or {}), set(fail)
        self.calls = 0

    def serial_ownership(self, serial):
        self.calls += 1
        if serial in self.fail:
            raise SerialError("cannot decode %s" % serial)
        if serial in self.unowned:
            return False, self.unowned[serial]
        return True, None


def _row(name, serial, bullet="N/A", type_="weapon", wtype="pistol", maker="Jakobs", rarity="Legendary",
         source="GunCodes_pistol.txt"):
    return {"itemName": name, "partString": '"%s",' % serial, "type": type_, "weaponType": wtype,
            "manufacturer": maker, "manufacturerWeaponType": "%s %s" % (maker, wtype.title()),
            "rarity": rarity, "bulletType": bullet, "timestamp": "2025-01-01 00:00:00", "source": source}


def _tmp_catalog(config, tmp_path, rows, ops=None, rules=None, data=None, codec=None):
    path = tmp_path / "bl4-serial-matches.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    cfg = dataclasses.replace(config, data_dir=tmp_path)
    deps = {"codec": codec, "data": data or StubData(), "rules": rules or StubRules(), "ops": ops or StubOps()}
    return _module(cfg, deps)


# ---------------------------------------------------------------------------------------------
# framework conformance
# ---------------------------------------------------------------------------------------------

def test_conforms_to_port_and_declares_neighbours(catalog):
    assert conformance_problems(catalog, CatalogPort) == []
    assert MODULE is CatalogModule
    assert (CatalogModule.name, CatalogModule.requires, CatalogModule.port) == (
        "catalog", ("codec", "data", "rules", "ops"), CatalogPort)
    assert CatalogModule.purpose.startswith("Search the community serial database")


def test_no_module_level_mutable_state():
    for mod in (sys.modules["bl4forge.modules.catalog"], _db, _match):
        mutable = [k for k, v in vars(mod).items()
                   if not k.startswith("__") and isinstance(v, (dict, list, set, bytearray))]
        assert mutable == [], "%s has module-level mutable state: %s" % (mod.__name__, mutable)
    with pytest.raises(TypeError):
        _match.TYPE_ALIASES["zz"] = ("x",)          # the alias table is read-only


def test_per_instance_state(config, tmp_path):
    """Two instances over different databases never see each other's rows or caches."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a = _tmp_catalog(config, tmp_path / "a", [_row("Alpha", "@UaaaA")])
    b = _tmp_catalog(config, tmp_path / "b", [_row("Beta", "@UbbbB"), _row("Gamma", "@UcccC")])
    assert (a.count(), b.count()) == (1, 2)
    assert [e.name for e in a.search(SearchQuery()).entries] == ["Alpha"]
    assert [e.name for e in b.search(SearchQuery()).entries] == ["Beta", "Gamma"]


# ---------------------------------------------------------------------------------------------
# CONTRACT invariants - one test each, named after the invariant
# ---------------------------------------------------------------------------------------------

def test_loads_9875(catalog, legacy):
    assert catalog.count() == 9875 == len(legacy.forge.load_db())
    assert catalog.diagnostics()["rows_in_file"] == 9883            # 8 raw rows carry no serial
    assert catalog.diagnostics()["skipped_no_serial"] == 8


def test_dedupes_serials(catalog, legacy):
    res = catalog.search(SearchQuery(limit=BIG, verify_element=False, include_unowned=True))
    serials = [e.serial for e in res.entries]
    assert len(serials) == len(set(serials)) == 8520        # 9,875 rows, 8,520 distinct serials
    assert catalog.count() == 9875 > len(serials)           # count() is ROWS, search is de-duplicated
    assert len({r["serial"] for r in legacy.forge.load_db()}) == 8520
    # a duplicated serial comes back once, from its FIRST row (legacy keeps the first)
    first_row = {}
    for r in legacy.forge.load_db():
        first_row.setdefault(r["serial"], r)
    for e in res.entries[:200] + res.entries[-200:]:
        assert e.name == first_row[e.serial]["itemName"]


def test_deterministic(catalog, doubled, config, legacy):
    for flags in (dict(element="cryo", limit=50), dict(query="anarchy", limit=25), dict(limit=BIG)):
        q = _query(flags)
        assert catalog.search(q) == catalog.search(q)
    # a brand new instance (cold caches) answers identically
    fresh = _module(config, {n: doubled.module(n) for n in CatalogModule.requires})
    for flags in (dict(element="fire", limit=100), dict(type_="shield", limit=100)):
        assert fresh.search(_query(flags)) == catalog.search(_query(flags))


def test_search_order_is_database_order(catalog, legacy):
    res = catalog.search(SearchQuery(limit=BIG, verify_element=False, include_unowned=True))
    expected, seen = [], set()
    for r in legacy.forge.load_db():
        if r["serial"] not in seen:
            seen.add(r["serial"])
            expected.append(r["serial"])
    assert [e.serial for e in res.entries] == expected


TYPE_EXPECT = {      # alias -> (CatalogEntry field, value) every returned entry must carry
    "ar": ("weapon_type", "assaultrifle"), "assault_rifle": ("weapon_type", "assaultrifle"),
    "assaultrifle": ("weapon_type", "assaultrifle"), "rifle": ("weapon_type", "assaultrifle"),
    "AR": ("weapon_type", "assaultrifle"), " ar ": ("weapon_type", "assaultrifle"),
    "repkit": ("type", "repair_kit"), "repair_kit": ("type", "repair_kit"),
    "repairkit": ("type", "repair_kit"), "Repkit": ("type", "repair_kit"),
    "repair kit": ("type", "repair_kit"),
    "grenade": ("type", "gadget"), "ordnance": ("type", "gadget"), "gadget": ("type", "gadget"),
    "classmod": ("type", "classmod"), "class_mod": ("type", "classmod"),
    "class mod": ("type", "classmod"), "com": ("type", "classmod"),
    "launcher": ("weapon_type", "heavy"), "rocket": ("weapon_type", "heavy"),
    "heavy": ("weapon_type", "heavy"),
    "sr": ("weapon_type", "sniper"), "sniper": ("weapon_type", "sniper"),
    "smg": ("weapon_type", "smg"),
    "sg": ("weapon_type", "shotgun"), "shotgun": ("weapon_type", "shotgun"),
    "ps": ("weapon_type", "pistol"), "pistol": ("weapon_type", "pistol"),
    "shield": ("type", "shield"), "enhancement": ("type", "enhancement"), "weapon": ("type", "weapon"),
}


@pytest.mark.parametrize("alias", sorted(TYPE_EXPECT))
def test_type_aliases_work(catalog, legacy, alias):
    field, value = TYPE_EXPECT[alias]
    res = catalog.search(SearchQuery(type=alias, limit=BIG, verify_element=False, include_unowned=True))
    assert res.entries, "type %r returned nothing" % alias
    assert all(getattr(e, field) == value for e in res.entries)
    raw = {"weapon_type": "weaponType", "type": "type"}[field]
    expected = {r["serial"] for r in legacy.forge.load_db() if r[raw] == value}
    assert {e.serial for e in res.entries} == expected          # nothing missed, nothing extra


def test_type_aliases_legacy_once_returned_none(catalog):
    """The two aliases legacy once returned no rows for (db spells them assaultrifle / repair_kit)."""
    for alias in ("ar", "assault_rifle", "repkit", "repair_kit", "grenade", "gadget", "sg", "ps"):
        assert catalog.search(SearchQuery(type=alias, limit=3)).entries, alias


def test_matches_legacy(catalog, legacy):
    assert len(BATTERY) >= 40
    for flags in BATTERY:
        _assert_parity(catalog, legacy, flags)


def test_matches_legacy_whole_database_unfiltered(catalog, legacy):
    """No filter at all, owned-only: every serial legacy would return, in the same order."""
    flags = dict(limit=BIG)
    res, rows = _assert_parity(catalog, legacy, flags)
    assert len(rows) == 8520 and not res.hidden_by_pack


def test_labels_are_hints(catalog, legacy):
    F = legacy.forge
    ops = catalog.dep("ops")
    bad_serials, bad_rows = {}, {}    # per db element label: serials / ROWS whose label the bitstream contradicts
    for el in ("fire", "electric", "cryo", "radiation", "corrosive", "impact"):
        rows = [e for e in F.load_db() if e["bulletType"] == el and not F._element_ok(e, el)]
        bad_rows[el], bad_serials[el] = len(rows), {e["serial"] for e in rows}
    assert sum(bad_rows.values()) > 0, "expected the database to contain mislabelled rows"

    for el, bad in bad_serials.items():
        mine = "shock" if el == "electric" else el
        verified = catalog.search(SearchQuery(element=el, limit=BIG, include_unowned=True))
        trusted = catalog.search(SearchQuery(element=el, limit=BIG, include_unowned=True, verify_element=False))
        got = {e.serial for e in verified.entries}
        for e in verified.entries:
            actual = ops.describe(e.serial).element
            if e.type == "weapon":
                assert actual == mine, (el, e.name)       # every surviving weapon really carries it
            else:
                assert actual is None                     # gear: no element in the bitstream, label trusted
        # every mislabelled serial was dropped, and counted (rows, as legacy would drop them)
        assert not got & bad, el
        assert {e.serial for e in trusted.entries} >= bad, el
        assert trusted.dropped_element_mismatch == 0
        assert verified.dropped_element_mismatch == bad_rows[el], el
        # and the label of what survives is still the database's (hint) label
        assert all(e.element == mine for e in verified.entries)
    assert bad_rows["fire"] > 0 and bad_rows["electric"] > 0      # the known mislabels (legacy: ~3.3%)


def test_labels_are_hints_with_stub_neighbours(config, tmp_path):
    """The bitstream wins over the label: the stub ops says the 'fire' row is really cryo."""
    rows = [_row("Liar", "@UliarA", bullet="fire"), _row("Honest", "@UhoneA", bullet="fire"),
            _row("Gear", "@UgearA", bullet="fire")]
    ops = StubOps({"@UliarA": "cryo", "@UhoneA": "fire", "@UgearA": None})     # gear: no element
    cat = _tmp_catalog(config, tmp_path, rows, ops=ops)
    res = cat.search(SearchQuery(element="fire"))
    assert [e.name for e in res.entries] == ["Honest", "Gear"]      # None = cannot tell -> trust label
    assert res.dropped_element_mismatch == 1
    res = cat.search(SearchQuery(element="fire", verify_element=False))
    assert [e.name for e in res.entries] == ["Liar", "Honest", "Gear"] and res.dropped_element_mismatch == 0
    ops.calls = 0
    cat.search(SearchQuery(verify_element=False))               # no element asked -> nothing verified
    cat.search(SearchQuery(type="shield", verify_element=True))
    assert ops.calls == 0


def test_no_verification_without_manifest(config, tmp_path):
    """Legacy: if the manifest is absent nobody can read an element, so drop nothing."""
    rows = [_row("Liar", "@UliarA", bullet="fire")]
    cat = _tmp_catalog(config, tmp_path, rows, ops=StubOps({"@UliarA": "cryo"}), data=StubData(False))
    res = cat.search(SearchQuery(element="fire"))
    assert [e.name for e in res.entries] == ["Liar"] and res.dropped_element_mismatch == 0


def test_filters_are_reported(config, legacy):
    with _restricted(config, legacy) as (cfg, forge):
        cat = forge.catalog
        # who is hidden, found independently of catalog: legacy describe over every distinct serial
        need = {s for s in {r["serial"] for r in legacy.forge.load_db()}
                if not legacy.partsdb.describe(s)["owned"]}
        assert len(need) == 26
        visible = cat.search(SearchQuery(limit=BIG))
        everything = cat.search(SearchQuery(limit=BIG, include_unowned=True))
        assert visible.hidden_by_pack == {"bounty_pack_3": 26}
        assert everything.hidden_by_pack == {}
        assert len(everything.entries) == 8520
        assert len(visible.entries) + sum(visible.hidden_by_pack.values()) == len(everything.entries)
        assert need == {e.serial for e in everything.entries} - {e.serial for e in visible.entries}
        assert forge.rules.pack_label("bounty_pack_3")          # the consumer can name the pack
        # per query, against legacy's last_skipped (keys are pack ids here, labels in legacy)
        for flags in (dict(limit=BIG), dict(type_="smg", element="cryo", limit=BIG),
                      dict(query="frangible", limit=25), dict(type_="smg", limit=BIG, include_unowned=True)):
            _assert_parity(cat, legacy, flags)
        frang = cat.search(SearchQuery(query="frangible", limit=25))
        assert sum(frang.hidden_by_pack.values()) >= 1 and frang.hidden_by_pack.keys() == {"bounty_pack_3"}
        assert cat.search(SearchQuery(query="frangible", include_unowned=True)).entries


def test_filters_are_reported_with_stub_rules(config, tmp_path):
    rows = [_row("Mine", "@UmineA"), _row("DlcA", "@UdlcaA"), _row("DlcB", "@UdlcbB"),
            _row("DlcA again", "@UdlcaA"), _row("Mystery", "@UmystA")]
    rules = StubRules({"@UdlcaA": "story_pack_1", "@UdlcbB": "story_pack_1", "@UmystA": None})
    cat = _tmp_catalog(config, tmp_path, rows, rules=rules)
    res = cat.search(SearchQuery())
    assert [e.name for e in res.entries] == ["Mine"]
    # counted once per distinct serial (the repeat row of @UdlcaA is a duplicate, like legacy);
    # a pack rules cannot name is reported under 'unknown', never lost
    assert res.hidden_by_pack == {"story_pack_1": 2, "unknown": 1}
    res = cat.search(SearchQuery(include_unowned=True))
    assert [e.name for e in res.entries] == ["Mine", "DlcA", "DlcB", "Mystery"] and res.hidden_by_pack == {}


def test_search_limit_semantics(catalog, legacy):
    big = catalog.search(SearchQuery(type="smg", limit=BIG, verify_element=False, include_unowned=True))
    for n in (1, 5, 25, 100):
        res = catalog.search(SearchQuery(type="smg", limit=n, verify_element=False, include_unowned=True))
        assert len(res.entries) == n and res.entries == big.entries[:n]
    assert catalog.search(SearchQuery(type="smg", limit=None, include_unowned=True)).entries == tuple(
        e for e in big.entries)
    assert catalog.search(SearchQuery(type="smg", limit="5", include_unowned=True)).entries == big.entries[:5]
    assert catalog.search(SearchQuery(type="smg", limit="lots", include_unowned=True)).entries == big.entries[:25]
    # limit <= 0 is an empty answer (legacy returned one row, because it checked the cap after appending)
    for n in (0, -3):
        assert catalog.search(SearchQuery(limit=n)) == SearchResult()
    assert len(legacy.forge.search(limit=0)) == 1


# ---------------------------------------------------------------------------------------------
# edges of the query language
# ---------------------------------------------------------------------------------------------

def test_element_aliases_resolve_through_vocab(catalog, legacy):
    base = {el: catalog.search(SearchQuery(element=el, limit=BIG)) for el in vocab.ELEMENTS}
    assert all(r.entries for r in base.values())
    for alias, canon in vocab.ELEMENT_ALIASES.items():
        for spelled in (alias, alias.upper(), " %s " % alias):
            assert catalog.search(SearchQuery(element=spelled, limit=BIG)) == base[canon], spelled
    # legacy's own alias table is a subset of the vocabulary and means the same thing
    for alias, db_label in legacy.forge.ELEM_ALIAS.items():
        assert vocab.ELEMENT_ALIASES[alias] == _db_element(db_label)
    assert {e.element for e in base["shock"].entries} == {"shock"}       # 'electric' in the db


def test_unknown_element_matches_nothing_like_legacy(catalog, legacy):
    assert catalog.search(SearchQuery(element="plasma", limit=BIG)) == SearchResult()
    assert legacy.forge.search(element="plasma", limit=BIG) == []
    # whitespace-only is "no filter", not "unknown"
    assert catalog.search(SearchQuery(element="  ", limit=3)).entries


def test_character_aliases_and_keyword_fallback(catalog, legacy):
    res = {c: catalog.search(SearchQuery(type="classmod", character=c, limit=BIG)) for c in
           ("gravitar", "dark_siren", "dark siren", "Dark-Siren", "exo_soldier", "exo soldier", "paladin")}
    assert res["dark siren"] == res["dark_siren"] == res["Dark-Siren"]
    assert res["exo soldier"] == res["exo_soldier"]
    counts = {c: len(r.entries) for c, r in res.items() if c in ("gravitar", "dark_siren", "exo_soldier", "paladin")}
    assert all(n > 100 for n in counts.values())
    assert all(vocab.normalize_character(c) for c in counts)
    # a keyword that is not a character is used against `source`, as in legacy
    mine = catalog.search(SearchQuery(type="classmod", character="siren", limit=BIG))
    assert [e.serial for e in mine.entries] == [r["serial"] for r in legacy.forge.search(
        type_="classmod", character="siren", limit=BIG)] and mine.entries
    assert catalog.search(SearchQuery(character="nobody", limit=BIG)) == SearchResult()


def test_substring_filters_and_whitespace(catalog):
    a = catalog.search(SearchQuery(query="anarchy", limit=BIG))
    assert a.entries and all("anarchy" in e.name.lower() for e in a.entries)
    assert catalog.search(SearchQuery(query="  AnArChy ", limit=BIG)) == a
    m = catalog.search(SearchQuery(manufacturer="JAKO", limit=BIG, include_unowned=True))
    assert m.entries and all("jakobs" in e.manufacturer.lower() for e in m.entries)
    r = catalog.search(SearchQuery(rarity="common", limit=BIG, include_unowned=True))
    assert {e.rarity for e in r.entries} == {"Uncommon"}              # substring semantics, as legacy


def test_search_rejects_non_query(catalog):
    with pytest.raises(TypeError):
        catalog.search({"query": "anarchy"})


# ---------------------------------------------------------------------------------------------
# stats() and find_by_serial()
# ---------------------------------------------------------------------------------------------

def _parse_cmd_catalog(text):
    tables, current = {}, None
    titles = {"By type:": "by_type", "By weapon type:": "by_weapon_type", "By manufacturer:": "by_manufacturer",
              "By element (bulletType):": "by_element", "Class-mod characters (from source):": "by_character"}
    for line in text.splitlines():
        if line.strip() in titles:
            current = titles[line.strip()]
            tables[current] = []
        elif line.startswith("Total codes:"):
            tables["total"] = int(line.split(":")[1])
        elif line.startswith("  ") and current:
            key, n = line.strip().rsplit(None, 1)
            tables[current].append((key, int(n)))
    return tables


def test_stats_equals_legacy_cmd_catalog(catalog, legacy, capsys):
    import argparse
    legacy.forge.cmd_catalog(argparse.Namespace())
    legacy_tables = _parse_cmd_catalog(capsys.readouterr().out)
    stats = catalog.stats()
    assert legacy_tables["total"] == catalog.count() == 9875
    for name in ("by_type", "by_weapon_type", "by_manufacturer", "by_character"):
        assert list(stats[name].items()) == legacy_tables[name], name       # same counts, same order
    # elements: the database spelling 'electric' is the vocab name 'shock'; 'N/A' stays 'N/A'
    mapped = [("N/A" if k == "N/A" else vocab.normalize_element(k), n) for k, n in legacy_tables["by_element"]]
    assert list(stats["by_element"].items()) == mapped
    # rarity: legacy never printed it; check against a plain count of the same rows
    assert stats["by_rarity"] == dict(Counter(r["rarity"] for r in legacy.forge.load_db()).most_common())
    assert sum(stats["by_type"].values()) == sum(stats["by_rarity"].values()) == 9875
    for table in ("by_type", "by_weapon_type", "by_rarity"):               # the keys the port promises
        assert table in stats
    stats["by_type"]["weapon"] = -1                                         # callers get copies
    assert catalog.stats()["by_type"]["weapon"] > 0


def test_find_by_serial(catalog, legacy):
    entry = catalog.find_by_serial(KNOWN_SERIAL)
    assert isinstance(entry, CatalogEntry) and entry.serial == KNOWN_SERIAL
    assert entry.type == "weapon" and entry.weapon_type == "shotgun" and "Anarchy" in entry.name
    assert catalog.find_by_serial('  "%s",  ' % KNOWN_SERIAL) == entry          # pasted from the json
    assert catalog.find_by_serial("@Unot-in-the-database") is None
    for junk in ("", "no serial here", None, 5, b"@U"):
        assert catalog.find_by_serial(junk) is None
    # every row is findable, and a duplicated serial resolves to its first row
    first_row = {}
    for r in legacy.forge.load_db():
        first_row.setdefault(r["serial"], r)
    for s, r in first_row.items():                  # all 8,520 distinct serials
        _assert_entry_is_row(catalog.find_by_serial(s), r)
    counts = Counter(r["serial"] for r in legacy.forge.load_db())
    dups = [s for s, n in counts.items() if n > 1]
    assert dups                                      # the database does repeat serials
    for s in dups:
        _assert_entry_is_row(catalog.find_by_serial(s), first_row[s])


# ---------------------------------------------------------------------------------------------
# malformed data and sick neighbours: tolerated deliberately, counted, tested
# ---------------------------------------------------------------------------------------------

def test_malformed_rows_are_skipped_and_counted(config, tmp_path):
    rows = [
        _row("Alpha Gun", "@UaaaA", bullet="electric"),
        _row("Alpha Gun copy", "@UaaaA", bullet="electric"),     # duplicate serial: a row, not a serial
        "this row is a string, not an object",
        {"itemName": "No serial", "partString": "nothing useful"},
        {"itemName": "Number serial", "partString": 12345},
        {"itemName": None, "partString": "@UbbbB", "bulletType": "plasma", "type": None, "rarity": 7},
        _row("Gear", "@UcccC", bullet="N/A", type_="shield", wtype="shield"),
        {"partString": '"@UddddD",'},                               # every other field missing
        _row("Weird spacing", "@UeeeE"),
    ]
    rows[-1]["partString"] = '"@UeeeE and more",'                 # cleaning stops at whitespace
    cat = _tmp_catalog(config, tmp_path, rows)
    assert cat.count() == 6                                        # rows with a serial, duplicates included
    d = cat.diagnostics()
    assert (d["rows_in_file"], d["rows_loaded"]) == (9, 6)
    assert (d["skipped_not_an_object"], d["skipped_no_serial"], d["unrecognised_element_label"]) == (1, 2, 1)
    allrows = cat.search(SearchQuery(limit=BIG, verify_element=False, include_unowned=True)).entries
    assert [e.serial for e in allrows] == ["@UaaaA", "@UbbbB", "@UcccC", "@UddddD", "@UeeeE"]
    alpha, odd, gear, bare, spaced = allrows
    assert alpha.element == "shock" and alpha.name == "Alpha Gun"            # electric -> shock
    assert odd.name == "?" and odd.element is None and odd.type == "" and odd.rarity == ""
    assert gear.element is None and gear.type == "shield"                     # N/A -> None
    assert (bare.name, bare.label, bare.element) == ("?", "", None)
    assert spaced.serial == "@UeeeE"
    assert cat.find_by_serial("@UaaaA").name == "Alpha Gun"                   # first of the duplicates
    assert cat.stats()["by_element"] == {"N/A": 4, "shock": 2}


def test_unreadable_database_raises_datamissing_and_is_not_cached(config, tmp_path):
    cfg = dataclasses.replace(config, data_dir=tmp_path)
    cat = _module(cfg, {"codec": None, "data": StubData(), "rules": StubRules(), "ops": StubOps()})
    # construction is lazy and safe; asking raises the shared error type, with the path in the message
    for call in (cat.count, lambda: cat.search(SearchQuery()), cat.stats, lambda: cat.find_by_serial("@Ux")):
        with pytest.raises(DataMissing, match="bl4-serial-matches.json"):
            call()
    assert cat.diagnostics()["element_check_errors"] == 0              # diagnostics never raise
    report = cat.health()                                              # health never raises either
    assert not report.ok and not report.checks[0].ok
    (tmp_path / "bl4-serial-matches.json").write_text(json.dumps([_row("Late", "@UlateA")]), encoding="utf-8")
    assert cat.count() == 1                                            # the file appeared: picked up
    (tmp_path / "bl4-serial-matches.json").write_text("{not json", encoding="utf-8")
    broken = _module(cfg, {"codec": None, "data": StubData(), "rules": StubRules(), "ops": StubOps()})
    with pytest.raises(DataMissing, match="not valid JSON"):
        broken.count()
    (tmp_path / "bl4-serial-matches.json").write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(DataMissing, match="JSON list"):
        _module(cfg, {"codec": None, "data": StubData(), "rules": StubRules(), "ops": StubOps()}).count()


def test_decode_failure_during_verification_never_crashes_a_search(config, tmp_path):
    """Legacy: a row that will not decode is ALLOWED (the codec is at fault, not the player).
    Here it is also counted, once per distinct serial, in diagnostics()."""
    rows = [_row("Good", "@UgoodA", bullet="cryo"), _row("Garbled", "@UbadAA", bullet="cryo"),
            _row("Garbled again", "@UbadAA", bullet="cryo"), _row("Also bad owner", "@UbadBB", bullet="cryo")]
    ops = StubOps({"@UgoodA": "cryo"}, fail=("@UbadAA", "@UbadBB"))
    rules = StubRules(fail=("@UbadBB",))
    cat = _tmp_catalog(config, tmp_path, rows, ops=ops, rules=rules)
    res = cat.search(SearchQuery(element="cryo"))
    assert [e.name for e in res.entries] == ["Good", "Garbled", "Also bad owner"]
    assert res.dropped_element_mismatch == 0 and res.hidden_by_pack == {}
    assert cat.diagnostics()["element_check_errors"] == 2             # two distinct serials, not 3 rows
    assert cat.diagnostics()["ownership_check_errors"] == 1
    cat.search(SearchQuery(element="cryo"))
    assert cat.diagnostics()["element_check_errors"] == 2             # memoised: not re-counted


def test_undecodable_serial_matches_legacy_rule(config, legacy, doubled, tmp_path):
    bad = "@Uzzzzzzzzzz"
    assert legacy.forge._element_ok({"serial": bad}, "cryo") is True
    assert legacy.forge._ownership_ok(bad) == (True, None)
    sub = tmp_path / "garbage"
    sub.mkdir()
    cat = _tmp_catalog(config, sub, [_row("Garbage", bad, bullet="cryo")], ops=doubled.ops,
                       rules=doubled.rules, data=doubled.data)
    res = cat.search(SearchQuery(element="cryo"))
    assert [e.serial for e in res.entries] == [bad] and res.dropped_element_mismatch == 0
    assert cat.diagnostics()["element_check_errors"] == 1 and cat.diagnostics()["ownership_check_errors"] == 1


def test_neighbours_are_asked_only_when_needed(config, tmp_path):
    rows = [_row("A", "@UaaaA", bullet="fire"), _row("B", "@UbbbB", bullet="fire")]
    ops, rules = StubOps({"@UaaaA": "fire", "@UbbbB": "fire"}), StubRules()
    cat = _tmp_catalog(config, tmp_path, rows, ops=ops, rules=rules)
    cat.search(SearchQuery(element="fire", include_unowned=True))
    assert (ops.calls, rules.calls) == (2, 0)                    # include_unowned: ownership not consulted
    cat.search(SearchQuery(element="fire"))
    assert (ops.calls, rules.calls) == (2, 2)                    # memoised element, new ownership checks
    cat.search(SearchQuery(element="fire", limit=1))
    assert (ops.calls, rules.calls) == (2, 2)                    # nothing left to ask


# ---------------------------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------------------------

def test_health_is_real_and_fast(doubled, catalog):
    assert doubled.states["catalog"].state == "ok", doubled.states["catalog"].detail
    start = time.perf_counter()
    report = catalog.health()
    assert time.perf_counter() - start < 1.0
    assert report.ok
    names = {c.name for c in report.checks}
    assert {"database_loads", "known_query", "type_aliases", "find_by_serial", "sample_rows_decode",
            "neighbours_verify"} <= names
    assert all(c.ok for c in report.checks)


def test_health_reports_a_sick_neighbour_without_raising(config, doubled):
    class Sick:
        def describe(self, serial):
            raise NotImplementedError("skeleton")

        def serial_ownership(self, serial):
            raise NotImplementedError("skeleton")

    cat = _module(config, {"codec": doubled.codec, "data": doubled.data, "rules": Sick(), "ops": Sick()})
    report = cat.health()                          # no raise
    assert not report.ok
    bad = {c.name for c in report.checks if not c.ok}
    assert bad == {"neighbours_verify"}            # the database itself is fine; verification is not
    # ...and a search still answers (unverified), never crashes
    assert cat.search(SearchQuery(element="cryo", limit=3)).entries
    assert cat.diagnostics()["element_check_errors"] >= 1


# ---------------------------------------------------------------------------------------------
# the same battery with the REAL rules and ops modules (skipped until they land)
# ---------------------------------------------------------------------------------------------

def test_with_real_neighbours(forge, config, legacy):
    for name in ("rules", "ops"):
        if forge.states[name].state != "ok":
            pytest.skip("real %s module is not healthy yet (%s: %s)"
                        % (name, forge.states[name].state, forge.states[name].detail))
    assert forge.states["catalog"].state == "ok"
    legacy.partsdb.set_owned_packs(config.owned_packs)
    catalog = forge.catalog
    assert catalog.dep("rules") is forge.rules and catalog.dep("ops") is forge.ops
    assert catalog.count() == 9875
    for flags in BATTERY:       # real rules name packs with ids; legacy keys by label: compare totals
        _assert_parity(catalog, legacy, flags, exact_pack_keys=False)
    assert catalog.diagnostics()["element_check_errors"] == 0
    assert catalog.diagnostics()["ownership_check_errors"] == 0
    # ownership with a smaller owned set, through the real rules
    with _restricted(config, legacy, real=True) as (cfg, restricted):
        cat = restricted.catalog
        for flags in (dict(limit=BIG), dict(type_="smg", element="cryo", limit=BIG),
                      dict(query="frangible", limit=25)):
            _assert_parity(cat, legacy, flags, exact_pack_keys=False)
        assert sum(cat.search(SearchQuery(limit=BIG)).hidden_by_pack.values()) == 26
