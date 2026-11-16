"""Tests for the `rules` module: CONTRACT invariants + parity with the legacy partsdb/forge oracle.

Legacy (`legacy.partsdb`) is the oracle for `validate` and for ownership over all 9,875 database
rows. Intentional differences are listed in src/bl4forge/modules/rules/CONTRACT.md "Deviations from
legacy"; the ones that can be observed have their own test below. The legacy owned-pack set is a
process global, so every test that changes it goes through `legacy_owned`, which restores it.
"""
from __future__ import annotations

import dataclasses
from typing import Dict, List, NamedTuple, Optional, Tuple

import pytest

from bl4forge.core.config import DEFAULT_OWNED_PACKS, Config
from bl4forge.core.errors import ConfigError, SerialError
from bl4forge.core.forge import OK, Forge
from bl4forge.core.module import ModuleContext, conformance_problems
from bl4forge.core.ports import RulesPort
from bl4forge.core.types import Block, Part, SUBTYPE_INT, SUBTYPE_LIST, SUBTYPE_NONE, TOK_PART
from bl4forge.modules.data import DataModule
from bl4forge.modules import rules as rules_pkg
from bl4forge.modules.rules import CONTENT_PACKS, MODULE, NO_MANIFEST, RulesModule
from tests.dataset import D, rules_known

K = rules_known()

STORY = "story_pack_1"
BOUNTY_3 = "bounty_pack_3"
WITHOUT_BOUNTY_3 = tuple(p for p in DEFAULT_OWNED_PACKS if p != BOUNTY_3)

# Owned-pack sets the ownership parity runs under. () exercises "base game is always owned".
OWNED_SETS = {
    "default": DEFAULT_OWNED_PACKS,
    "no_bounty_pack_3": WITHOUT_BOUNTY_3,
    "base_only": ("coregame",),
    "nothing_listed": (),
    "story_only": (STORY,),
}


# ---- helpers ----------------------------------------------------------------------------------

def make_rules(forge: Forge, config: Config, owned=None, data=None) -> RulesModule:
    """A RulesModule on its own context. Never mutates the shared session config or forge."""
    cfg = config if owned is None else dataclasses.replace(config, owned_packs=tuple(owned))
    return RulesModule(ModuleContext("rules", cfg, {"codec": forge.codec, "data": data or forge.data}))


def with_part(codec, serial: str, part: Part) -> str:
    """The same serial with one more PART block just before the terminator."""
    blocks = codec.decode(serial)
    return codec.encode(blocks[:-1] + (Block(token=TOK_PART, part=part),) + blocks[-1:])


def bare(index: int) -> Part:
    return Part(index=index, subtype=SUBTYPE_NONE)


def cross(category: int, index: int) -> Part:
    return Part(index=category, subtype=SUBTYPE_INT, value=index)


def split_ref(key: str) -> Tuple[int, int]:
    cat, idx = key.split(":")
    return int(cat), int(idx)


class TaggedData:
    """The real data module, except `part_meta` tags some extra refs with a pack (for what the data lacks)."""

    def __init__(self, real, tags: Dict[Tuple[int, int], str]):
        self._real, self._tags = real, tags

    def __getattr__(self, name):
        return getattr(self._real, name)

    def part_meta(self, category_id, index):
        meta = dict(self._real.part_meta(category_id, index))
        if (category_id, index) in self._tags:
            meta["pack"] = self._tags[(category_id, index)]
        return meta


@pytest.fixture
def legacy_owned(legacy):
    """Set the legacy (global) owned-pack set for one test and put the old one back afterwards."""
    saved = legacy.partsdb.owned_packs()

    def setter(packs):
        legacy.partsdb.set_owned_packs(packs)
    yield setter
    legacy.partsdb.set_owned_packs(saved)


@pytest.fixture(scope="module")
def rules(forge) -> RulesModule:
    return forge.rules


@pytest.fixture(scope="module")
def db_rows(legacy):
    return legacy.forge.load_db()


@pytest.fixture(scope="module")
def distinct(all_serials) -> List[str]:
    return list(dict.fromkeys(all_serials))


@pytest.fixture(scope="module")
def meta_refs(legacy) -> Dict[Tuple[int, int], dict]:
    """Every (category, index) the game tags in part_meta.json (legacy table; it is the oracle)."""
    return {split_ref(k): v for k, v in legacy.partsdb.part_meta().items()}


class DlcOnBase(NamedTuple):
    serial: str
    item_name: str                       # the community database's name for the item
    comp_refs: Tuple[Tuple[int, int], ...]   # its composition (rarity) parts: all base game
    dlc_refs: Tuple[Tuple[int, int], ...]    # its parts tagged with a content pack
    dlc_names: Tuple[str, ...]
    pack: str


@pytest.fixture(scope="module")
def dlc_on_base_items(legacy, db_rows) -> List[DlcOnBase]:
    """REAL database items that carry a DLC part while every identity of the item reads as base game.

    Found with the legacy oracle, not with the module under test: the item's composition parts
    (the ones that name a legendary) are all base game, and the community database's item name does
    not contain the DLC part's name. Only a per-part check can catch these.
    """
    P = legacy.partsdb
    found, seen = [], set()
    for row in db_rows:
        serial = row["serial"]
        if serial in seen:
            continue
        seen.add(serial)
        d = P.describe(serial)
        refs = [(p.category_id, p.index, p.raw) for p in d["parts"]]
        dlc = [(c, i) for c, i, _ in refs if P.meta_for(c, i).get("pack")]
        if not dlc:
            continue
        comps = [(c, i) for c, i, raw in refs if raw and raw.startswith("comp_")]
        names = tuple(P.meta_for(c, i).get("name", "") for c, i in dlc)
        looks_base = (comps and all(not P.meta_for(c, i).get("pack") for c, i in comps)
                      and not set(comps) & set(dlc)
                      and not any(n and n.lower() in row["itemName"].lower() for n in names))
        if looks_base:
            pack = sorted({P.meta_for(c, i)["pack"] for c, i in dlc})[0]
            found.append(DlcOnBase(serial, row["itemName"], tuple(comps), tuple(dlc), names, pack))
    return found


# ---- port + wiring ----------------------------------------------------------------------------

def test_conforms_to_port(forge):
    assert forge.states["rules"].state == OK, forge.states["rules"].detail
    assert conformance_problems(forge.rules, RulesPort) == []
    assert isinstance(forge.rules, RulesPort)


def test_module_declaration():
    assert MODULE is RulesModule
    assert RulesModule.name == "rules"
    assert RulesModule.requires == ("codec", "data")
    assert RulesModule.port is RulesPort


def test_no_module_level_mutable_state():
    """AGENT_RULES 5: constants only (tuples, frozensets, read-only mappings); no dict/list/set globals."""
    import bl4forge.modules.rules._known as known
    import bl4forge.modules.rules._walk as walk
    for mod in (rules_pkg, known, walk):
        for name, value in vars(mod).items():
            if name.startswith("__"):
                continue                      # interpreter bookkeeping (__path__, __all__ ...)
            assert not isinstance(value, (dict, list, set, bytearray)), "%s.%s is mutable" % (mod.__name__, name)


# ---- invariants (each named after CONTRACT.md) ------------------------------------------------

def test_ownership_is_per_part(forge, config, dlc_on_base_items):
    """A DLC part on an item with a base-game name and base-game composition is still caught."""
    assert dlc_on_base_items, "the data should contain real items with a DLC part under a base-game name"
    example = dlc_on_base_items[0]
    # Everything that names the item is base game, and so is the name the community gave it ...
    assert all(forge.rules.pack_of(c, i) == "coregame" for c, i in example.comp_refs)
    assert example.pack not in example.item_name
    # ... and a name- or item-level judgement would pass it. A per-part judgement must not.
    for ex in dlc_on_base_items:
        owner = make_rules(forge, config, owned=[p for p in config.owned_packs if p != ex.pack])
        assert owner.serial_ownership(ex.serial) == (False, ex.pack), ex
        assert all(owner.is_owned(c, i) for c, i in ex.comp_refs)
        assert not any(owner.is_owned(c, i) for c, i in ex.dlc_refs)
        # the default set owns that pack, so the same item is fine there
        assert forge.rules.serial_ownership(ex.serial) == (True, None)


def test_ownership_is_per_part_synthetic(forge, config, rules):
    """Any base-game serial plus one DLC part becomes unowned, whichever way the part is addressed."""
    base = K.BASE_SERIAL
    assert rules.serial_ownership(base) == (True, None)
    cat, idx = K.STORY_PACK_REF
    for syn in (with_part(forge.codec, base, bare(idx)), with_part(forge.codec, base, cross(cat, idx))):
        assert rules.serial_ownership(syn) == (False, STORY)


def test_story_pack_1_not_owned_by_default(forge, config, rules, meta_refs):
    assert STORY not in config.owned_packs and STORY not in DEFAULT_OWNED_PACKS
    assert STORY not in rules.owned_packs()
    refs = [ref for ref, meta in meta_refs.items() if meta.get("pack") == STORY]
    assert len(refs) >= 20, "the manifest tags Story Pack 1 parts"
    base = K.BASE_SERIAL
    for cat, idx in refs:
        assert rules.pack_of(cat, idx) == STORY
        assert rules.is_owned(cat, idx) is False
        assert rules.serial_ownership(with_part(forge.codec, base, cross(cat, idx))) == (False, STORY)
    # owning the pack turns the same answers around
    owner = make_rules(forge, config, owned=tuple(config.owned_packs) + (STORY,))
    assert owner.is_owned(*refs[0]) is True
    assert owner.serial_ownership(with_part(forge.codec, base, cross(*refs[0]))) == (True, None)


def test_bounty_pack_5_is_harmless(forge, config, rules, meta_refs, distinct):
    """It is listed as owned before it ships; no part carries it, so listing or dropping it changes nothing."""
    assert "bounty_pack_5" in config.owned_packs
    assert not [ref for ref, meta in meta_refs.items() if meta.get("pack") == "bounty_pack_5"]
    trimmed = make_rules(forge, config, owned=[p for p in config.owned_packs if p != "bounty_pack_5"])
    assert [trimmed.serial_ownership(s) for s in distinct] == [rules.serial_ownership(s) for s in distinct]
    assert rules.pack_label("bounty_pack_5") == "bounty_pack_5"      # unlisted key: labelled by itself


def test_owned_set_comes_from_config(forge, config, rules, dlc_on_base_items):
    ex = dlc_on_base_items[0]
    assert isinstance(rules.owned_packs(), frozenset)
    assert rules.owned_packs() == frozenset(config.owned_packs)
    saved = tuple(config.owned_packs)

    # A whole Forge built from a different config answers differently ...
    cfg = dataclasses.replace(config, owned_packs=WITHOUT_BOUNTY_3)
    other = Forge.build(cfg, only=("rules",))
    assert other.states["rules"].state == OK, other.states["rules"].detail
    assert other.rules.owned_packs() == frozenset(WITHOUT_BOUNTY_3)
    assert other.rules.serial_ownership(ex.serial) == (False, ex.pack)
    assert not other.rules.is_owned(*ex.dlc_refs[0])
    # ... while the session forge and config are untouched.
    assert rules.serial_ownership(ex.serial) == (True, None)
    assert rules.owned_packs() == frozenset(saved) and tuple(config.owned_packs) == saved

    # Owning Story Pack 1 flips its parts; owning nothing extra leaves only the base game.
    cat, idx = K.STORY_PACK_REF
    story = make_rules(forge, config, owned=saved + (STORY,))
    assert story.is_owned(cat, idx) and not rules.is_owned(cat, idx)
    base_only = make_rules(forge, config, owned=())
    assert base_only.owned_packs() == frozenset()
    assert base_only.is_owned(cat, 1) is True or base_only.pack_of(cat, 1) != "coregame"


def test_owned_set_is_per_instance(forge, config, rules):
    a, b = make_rules(forge, config), make_rules(forge, config)
    a.set_owned_packs(["coregame"])
    assert a.owned_packs() == frozenset(["coregame"])
    assert b.owned_packs() == frozenset(config.owned_packs)
    assert rules.owned_packs() == frozenset(config.owned_packs)
    a.set_owned_packs(iter(("coregame", STORY)))          # any iterable of keys
    assert a.owned_packs() == frozenset(("coregame", STORY))
    for bad in ("coregame", ["coregame", 3], [None]):
        with pytest.raises(ConfigError):
            a.set_owned_packs(bad)
    assert a.owned_packs() == frozenset(("coregame", STORY))      # a refused change changes nothing


def test_base_game_is_always_owned(forge, config):
    """Legacy ignored coregame at serial level but not in is_owned; both now agree it is always owned."""
    r = make_rules(forge, config, owned=())
    assert r.is_owned(3, 78) is True and r.pack_of(3, 78) == "coregame"
    assert r.serial_ownership(K.BASE_SERIAL) == (True, None)
    assert r.serial_ownership(K.STORY_PACK_SERIAL) == (False, STORY)


def test_pack_of_comes_from_part_meta_only(rules, meta_refs):
    """The pack is whatever part_meta says; a missing tag is base game; names and unknown refs never matter."""
    for (cat, idx), meta in meta_refs.items():
        assert rules.pack_of(cat, idx) == (meta.get("pack") or "coregame")
    for ref in ((None, 1), (999999, 3), (3, 99999), (0, 0), (-1, -1)):
        assert rules.pack_of(*ref) == "coregame" and rules.is_owned(*ref) is True


def test_first_missing_pack_is_alphabetical(forge, config):
    """Several missing packs -> the alphabetically first one; an owned pack is never named."""
    codec = forge.codec
    b3 = with_part(codec, K.STORY_PACK_SERIAL, bare(K.BOUNTY_REF[1]))        # wrong category: base game
    two = with_part(codec, K.STORY_PACK_SERIAL, cross(*K.BOUNTY_REF))        # + a bounty_pack_3 barrel
    assert b3 is not None
    nothing = make_rules(forge, config, owned=("coregame",))
    assert nothing.serial_ownership(two) == (False, BOUNTY_3)               # b < s
    bounty_owner = make_rules(forge, config, owned=("coregame", BOUNTY_3))
    assert bounty_owner.serial_ownership(two) == (False, STORY)
    assert make_rules(forge, config, owned=("coregame", BOUNTY_3, STORY)).serial_ownership(two) == (True, None)


def test_pack_label(rules, legacy):
    assert rules.pack_label("coregame") == "Base game"
    for key, label in legacy.partsdb.CONTENT_PACKS.items():
        assert rules.pack_label(key) == label
        assert CONTENT_PACKS[key] == label
    assert set(CONTENT_PACKS) == set(legacy.partsdb.CONTENT_PACKS)
    assert rules.pack_label("some_future_pack") == "some_future_pack"


# ---- validate: structural only ----------------------------------------------------------------

def test_validate_structural_only(forge, rules, legacy, db_rows, meta_refs):
    doc = " ".join((RulesModule.validate.__doc__ or "").split())
    assert "STRUCTURAL" in doc and "in-game validity" in doc and "Passing says nothing" in doc
    codec, P = forge.codec, legacy.partsdb
    assert rules.validate(K.BASE_SERIAL) == []                # passing means "no structural problem found"

    # A non-pearl with two composition parts is flagged ...
    flagged = rules.validate(K.TWO_COMPS_SERIAL)
    assert len(flagged) == 1 and "2 composition parts" in flagged[0] and "non-pearlescent" in flagged[0]
    assert flagged == P.validate(K.TWO_COMPS_SERIAL)

    # ... a pearlescent may carry two (named pearl part + plain legendary one) and is not.
    pearls = [(ref, m) for ref, m in meta_refs.items() if m.get("rarity") == "Pearl"
              and (P.part_table(ref[0]).get(ref[1]) or "").startswith("comp_")]
    assert len(pearls) >= 15
    # one real, non-pearl item with exactly one composition part for each category that has a pearl
    needed = {cat for (cat, _idx), _m in pearls}
    donors: Dict[int, str] = {}
    for row in db_rows:
        if len(donors) == len(needed):
            break
        cat = codec.get_category_id(codec.decode(row["serial"]))
        if cat in needed and cat not in donors:
            d = P.describe(row["serial"])
            comps = [p for p in d["parts"] if p.raw and p.raw.startswith("comp_")]
            if len(comps) == 1 and d["rarity"] != "Pearl":
                donors[cat] = row["serial"]
    checked = 0
    for (cat, idx), meta in pearls:
        if cat not in donors:
            continue
        syn = with_part(codec, donors[cat], bare(idx))
        got = rules.validate(syn)
        assert not any("composition parts" in p for p in got), (cat, idx, got)
        assert got == P.validate(syn)
        checked += 1
    assert checked >= 15
    # Rarity is the game's explicit field, not the name: Solar Temper is named comp_05_legendary_temper
    # (the SAME tier word as the legendary it is paired with) and is tagged Pearl. Reading rarity off the
    # name would tie, take the first, and flag it.
    assert P.part_table(26).get(84) == "comp_05_legendary_temper" and meta_refs[(26, 84)]["rarity"] == "Pearl"
    assert rules.validate(K.PEARL_TWO_COMPS_SERIAL) == [] == P.validate(K.PEARL_TWO_COMPS_SERIAL)


def test_validate_problem_kinds_match_legacy(forge, rules, legacy):
    """Every kind of problem, on synthetic serials, word for word as legacy reports it."""
    codec, P = forge.codec, legacy.partsdb
    base = K.BASE_SERIAL
    blocks = codec.decode(base)
    cases = {
        "unknown part": with_part(codec, base, bare(9999)),
        "two elements": with_part(codec, with_part(codec, base, cross(1, 10)), cross(1, 12)),
        "three elements": with_part(codec, with_part(codec, with_part(codec, base, cross(1, 10)), cross(1, 12)),
                                    cross(1, 14)),
        "one element": with_part(codec, base, cross(1, 11)),
        "level 0": codec.relevel(base, 0),
        "level 256": codec.relevel(base, 256),
        "level 255": codec.relevel(base, 255),
        "level 1": codec.relevel(base, 1),
        "level 100000": codec.relevel(base, 100000),
        "no level": codec.encode(codec.with_int_at(blocks, 2, 7)),
        "no composition": None,
        "category link": with_part(codec, base, bare(243)),
    }
    # an item with no composition part at all (62 of the community codes)
    for row in legacy.forge.load_db():
        if P.validate(row["serial"]) and "no composition" in P.validate(row["serial"])[0]:
            cases["no composition"] = row["serial"]
            break
    problems_seen = set()
    for label, serial in cases.items():
        got = rules.validate(serial)
        assert got == P.validate(serial), label
        problems_seen.update(g.split(" ")[0] + " " + g.split(" ")[1] for g in got)
    assert rules.validate(cases["unknown part"]) == ["part index 9999 does not exist in the Jakobs Pistol table"]
    assert rules.validate(cases["level 0"]) == ["level 0 is outside the usable range 1-255"]
    assert rules.validate(cases["no level"]) == ["no level field could be located"]
    assert rules.validate(cases["category link"]) == []        # a firmware pointer is not an unknown part
    assert rules.validate(cases["level 255"]) == [] and rules.validate(cases["level 1"]) == []
    assert len(rules.validate(cases["two elements"])) == 1 and "2 element parts" in rules.validate(cases["two elements"])[0]
    assert len(problems_seen) >= 6


def test_validate_checks_unknown_parts_in_the_right_table(forge, rules):
    """An unknown cross-category part is reported against the table it was looked up in (legacy named the item's)."""
    cat, name = (9103, "Breakfree SMG") if D.synthetic else (20, "Daedalus SMG")
    got = rules.validate(with_part(forge.codec, K.BASE_SERIAL, cross(cat, 9999)))
    assert got == ["part index 9999 does not exist in the %s table" % name]


# ---- parity with legacy over the whole database -----------------------------------------------

def test_matches_legacy_validate_all_serials(rules, legacy, all_serials):
    """`matches_legacy` for validate: identical problem lists on all 9,875 rows."""
    assert len(all_serials) == 9875
    cache: Dict[str, List[str]] = {}
    mismatches = []
    for s in all_serials:
        if s not in cache:
            cache[s] = rules.validate(s)
            if cache[s] != legacy.partsdb.validate(s):
                mismatches.append(s)
    assert not mismatches, "%d serials differ from legacy, e.g. %s" % (len(mismatches), mismatches[:3])
    flat = [p for v in cache.values() for p in v]
    assert flat and all(p.startswith("no composition part") for p in flat)     # what the database actually triggers


def _legacy_ownership(P, serial) -> Tuple[bool, Optional[str]]:
    info = P.describe(serial)
    return info["owned"], (None if info["owned"] else info["content_pack"])


def test_matches_legacy_ownership_all_serials(forge, config, legacy, legacy_owned, all_serials, distinct):
    """`matches_legacy` for ownership: owned flag and missing pack agree on all 9,875 rows, for several owned sets.

    The default set is checked against legacy on every distinct serial. For the other sets legacy is
    re-run on every serial that carries a DLC part plus a stride sample of the rest (a serial with no
    DLC part is owned under every set by construction; the sample shows the oracle agrees).
    """
    P = legacy.partsdb
    legacy_owned(DEFAULT_OWNED_PACKS)
    default_rules = make_rules(forge, config, owned=DEFAULT_OWNED_PACKS)
    expected = {s: _legacy_ownership(P, s) for s in distinct}
    dlc_serials = [s for s in distinct if P.describe(s).get("content_pack", "coregame") != "coregame"]
    assert dlc_serials, "the database holds items with DLC parts"
    sample = list(dict.fromkeys(dlc_serials + distinct[::10]))

    for name, packs in OWNED_SETS.items():
        r = default_rules if name == "default" else make_rules(forge, config, owned=packs)
        legacy_owned(packs)
        serials = distinct if name == "default" else sample
        not_owned = 0
        for s in serials:
            want = expected[s] if name == "default" else _legacy_ownership(P, s)
            got = r.serial_ownership(s)
            assert got == want, (name, s, got, want)
            if not got[0]:
                not_owned += 1
                assert got[1] in CONTENT_PACKS, "the missing pack must be a real pack key"
        if name == "no_bounty_pack_3":
            assert not_owned == len(dlc_serials)       # exactly the bounty_pack_3 items fall out
        if name == "default":
            assert not_owned == 0                      # nothing in the database is outside the default set
    # and the row-level view the catalog uses: duplicates in the database get the same verdict
    assert [default_rules.serial_ownership(s) for s in all_serials] == [expected[s] for s in all_serials]


def test_matches_legacy_pack_of_and_is_owned(forge, config, legacy, legacy_owned, meta_refs):
    P = legacy.partsdb
    refs = list(meta_refs) + [(None, 1), (999999, 3), (3, 99999), (0, 0)]
    for name, packs in OWNED_SETS.items():
        legacy_owned(packs)
        r = make_rules(forge, config, owned=packs)
        assert r.owned_packs() == frozenset(P.owned_packs()) == frozenset(packs)
        for cat, idx in refs:
            assert r.pack_of(cat, idx) == P.pack_of(cat, idx)
            if P.pack_of(cat, idx) != "coregame":
                assert r.is_owned(cat, idx) == P.is_owned(cat, idx), (name, cat, idx)
            else:   # the one deliberate difference: base game is owned even when not listed
                assert r.is_owned(cat, idx) is True


# ---- list parts (documented deviation) --------------------------------------------------------

def test_list_parts_are_judged_per_listed_part(forge, config, distinct):
    """`{cat:[a b c]}`: a, b, c are parts of category `cat`. Legacy looked `cat` up in the item's own table."""
    codec = forge.codec
    found = None
    for s in distinct:
        blocks = codec.decode(s)
        for b in blocks:
            if b.token == TOK_PART and b.part.subtype == SUBTYPE_LIST and len(b.part.values) >= 2:
                found = (s, b.part)
                break
        if found:
            break
    assert found, "the database has gear with list parts"
    serial, part = found
    assert forge.rules.serial_ownership(serial) == (True, None)
    tagged = TaggedData(forge.data, {(part.index, part.values[1]): STORY})        # one listed part is DLC
    r = make_rules(forge, config, data=tagged)
    assert r.pack_of(part.index, part.values[1]) == STORY
    assert r.serial_ownership(serial) == (False, STORY)
    assert r.is_owned(part.index, part.values[0]) is True
    # every listed value resolves in the list's category table, and nothing in the database is flagged
    # as unknown for it
    table = forge.data.part_table(part.index)
    assert all(v in table for v in part.values)
    assert forge.rules.validate(serial) == []


# ---- errors, missing data, health -------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "@U", "not a serial", "@Ug" + "x" * 5, None, 42])
def test_errors_are_serialerror(rules, bad):
    with pytest.raises(SerialError):
        rules.serial_ownership(bad)
    with pytest.raises(SerialError):
        rules.validate(bad)


def test_truncated_serial_raises_serialerror(rules):
    for fn in (rules.serial_ownership, rules.validate):
        with pytest.raises(SerialError):
            fn(K.BASE_SERIAL[:-3])


def test_missing_data_never_raises(forge, config, tmp_path, distinct):
    """With no manifest every part reads as base game and validate says it cannot validate; nothing raises."""
    empty = DataModule(ModuleContext("data", dataclasses.replace(config, data_dir=tmp_path), {}))
    assert not empty.available()
    r = make_rules(forge, config, data=empty)
    assert r.pack_of(20, 59) == "coregame" and r.is_owned(20, 59) is True
    assert r.pack_label("coregame") == "Base game"
    assert r.serial_ownership(distinct[0]) == (True, None)
    assert r.validate(distinct[0]) == [NO_MANIFEST]
    report = r.health()
    assert report.ok is False and any(c.name == "manifest" and not c.ok for c in report.checks)


def test_health_is_honest(forge, config, rules):
    report = rules.health()
    assert report.ok, report.summary
    names = {c.name for c in report.checks}
    assert {"manifest", "pack-label", "base-game-owned", "story-pack-1", "ownership-per-part",
            "list-parts", "structure", "errors-are-serialerror"} <= names
    assert all(c.ok for c in report.checks)
    # health follows the instance's owned set (Story Pack 1 owned -> its serial is owned, still a pass)
    owner = make_rules(forge, config, owned=tuple(config.owned_packs) + (STORY,))
    assert owner.health().ok
    nothing_extra = make_rules(forge, config, owned=("coregame",))
    assert nothing_extra.health().ok
    # a sick neighbour is reported, never raised
    class Broken:
        def __getattr__(self, name):
            raise RuntimeError("boom")
    sick = make_rules(forge, config, data=Broken())
    bad = sick.health()
    assert bad.ok is False and bad.checks


def test_known_answers_still_true_in_the_data(forge, rules, legacy, db_rows):
    """The constants health() relies on are real: re-derive them from the data and the oracle."""
    P = legacy.partsdb
    rows = {r["serial"]: r for r in db_rows}
    assert K.BASE_SERIAL in rows and K.BOUNTY_SERIAL in rows
    assert rows[K.BOUNTY_SERIAL]["itemName"] == "Frangible"
    assert P.meta_for(*K.STORY_PACK_REF)["pack"] == K.STORY_PACK == "story_pack_1"
    assert P.meta_for(*K.BOUNTY_REF)["pack"] == K.BOUNTY_PACK == "bounty_pack_3"
    assert K.STORY_PACK_SERIAL not in rows
    # the story-pack serial is the base serial + exactly the Shoals barrel
    assert forge.codec.parts_string(forge.codec.decode(K.STORY_PACK_SERIAL)) == \
        forge.codec.parts_string(forge.codec.decode(K.BASE_SERIAL)).rstrip("|") + " {%d}|" % K.STORY_PACK_REF[1]
    assert rules.pack_label("coregame") == "Base game"
    assert P.validate(K.TWO_COMPS_SERIAL) == rules.validate(K.TWO_COMPS_SERIAL)
    assert P.validate(K.PEARL_TWO_COMPS_SERIAL) == []
