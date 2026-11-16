"""Tests for the `ops` module (src/bl4forge/modules/ops).

The legacy `partsdb.py` is the parity oracle (fixture `legacy`); everything the contract promises is
compared against it over the whole community database (`all_serials`, 9,875 codes). Tests named
after CONTRACT.md "Invariants" come first, then parity sweeps, then the deliberate deviations and
edge cases. `rules` is a sibling built in parallel: the module is developed against the legacy-backed
RulesPort double (`tests.doubles`), and `test_with_real_rules` re-runs the key assertions against the
real thing as soon as it is healthy.

Legacy elements are 'Cryo'/'Impact' labels; ops returns vocab names ('cryo'/'impact'), so every
element comparison goes through `vocab.normalize_element` and states that mapping explicitly.
"""
import ast
import dataclasses
import inspect
import random
from pathlib import Path

import pytest

from bl4forge.core import vocab
from bl4forge.core.errors import ForgeError, SerialError
from bl4forge.core.forge import Forge
from bl4forge.core.module import Module, ModuleContext, conformance_problems
from bl4forge.core.ports import OpsPort, RulesPort
from bl4forge.core.types import (
    Block, HealthReport, ItemInfo, Part, PartRef, SUBTYPE_INT, SUBTYPE_NONE, TOK_PART, TOK_SEP1,
)
from bl4forge.modules import ops as ops_pkg
from bl4forge.modules.ops import MODULE, OpsModule, _known, _odds
from tests.doubles import LegacyRules, build_forge

SEED_POS = 5
DASH = "—"
OPS_DIR = Path(ops_pkg.__file__).resolve().parent
ELEMENT_PARTS = {10: "corrosive", 11: "cryo", 12: "fire", 13: "radiation", 14: "shock"}
SCALE_ELEMENTS = ("cryo", "fire", "radiation", "shock", "corrosive", "impact")


# ---- fixtures ---------------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def _legacy_owned_set(legacy, config):
    """The legacy oracle keeps its owned-pack set in a module global; pin it to the config's."""
    legacy.partsdb.set_owned_packs(config.owned_packs)
    yield


@pytest.fixture(scope="module")
def forge(config, legacy):
    """Real codec + data, the legacy-backed double for rules, and the real ops under test."""
    return build_forge(config, legacy, doubles=("rules",))


@pytest.fixture(scope="module")
def ops(forge):
    return forge.module("ops")          # usable even if its health is red, so failures name the real cause


@pytest.fixture(scope="module")
def codec(forge):
    return forge.codec


@pytest.fixture(scope="module")
def data(forge):
    return forge.data


@pytest.fixture(scope="module")
def infos(ops, all_serials):
    return [ops.describe(s) for s in all_serials]


@pytest.fixture(scope="module")
def legacy_infos(legacy, all_serials):
    return [legacy.partsdb.describe(s) for s in all_serials]


@pytest.fixture(scope="module")
def info_by(all_serials, infos):
    return dict(zip(all_serials, infos))


@pytest.fixture(scope="module")
def legacy_by(all_serials, legacy_infos):
    return dict(zip(all_serials, legacy_infos))


@pytest.fixture(scope="module")
def distinct(all_serials):
    return list(dict.fromkeys(all_serials))


@pytest.fixture(scope="module")
def weapons(distinct, info_by):
    """Distinct serials that describe as weapons (element is a vocab name, never None)."""
    return [s for s in distinct if info_by[s].element is not None]


@pytest.fixture(scope="module")
def by_category(distinct, info_by):
    out = {}
    for s in distinct:
        out.setdefault(info_by[s].category_id, []).append(s)
    return out


@pytest.fixture(scope="module")
def synthetic(codec, data, legacy, distinct, info_by, by_category):
    """Serials built from real database serials by pointing a part at a real part_meta entry.

    The database holds no pearlescent and no item that needs unowned content, so the interesting
    cases are made from real parts: for every part_meta entry that is a Pearl or carries a content
    pack, (a) REPLACE the first composition part of a database serial of that category with it, and
    (b) APPEND it as an extra part. Returns a list of (label, serial).
    """
    comp_at = {}                       # category -> (serial, token_index of an own-table comp part)
    for s in distinct:
        info = info_by[s]
        if info.category_id in comp_at:
            continue
        blocks = codec.decode(s)
        for p in info.parts:
            if (p.raw and p.raw.startswith("comp_") and p.category_id == info.category_id
                    and blocks[p.token_index].part.subtype == SUBTYPE_NONE):
                comp_at[info.category_id] = (s, p.token_index)
                break
    out = []
    for key, meta in sorted(legacy.partsdb.part_meta().items()):
        if not (meta.get("pack") or meta.get("rarity") == "Pearl"):
            continue
        cat, idx = (int(x) for x in key.split(":"))
        table = data.part_table(cat)
        if cat not in by_category or idx not in table:
            continue
        out.append(("append %s %s" % (key, meta.get("name")), append_part(codec, by_category[cat][0], idx)))
        if cat in comp_at and table[idx].startswith("comp_"):
            s, at = comp_at[cat]
            out.append(("replace %s %s" % (key, meta.get("name")), replace_part_index(codec, s, at, idx)))
    return out


# ---- helpers ----------------------------------------------------------------------------------

def replace_part_index(codec, serial, token_index, new_index):
    blocks = codec.decode(serial)
    b = blocks[token_index]
    nb = dataclasses.replace(b, part=dataclasses.replace(b.part, index=new_index))
    return codec.encode(blocks[:token_index] + (nb,) + blocks[token_index + 1:])


def append_part(codec, serial, index, subtype=SUBTYPE_NONE, value=0):
    blocks = codec.decode(serial)
    assert blocks[-1].token == TOK_SEP1
    new = Block(TOK_PART, part=Part(index=index, subtype=subtype, value=value))
    return codec.encode(blocks[:-1] + (new,) + blocks[-1:])


def part_blocks(codec, serial):
    return [b for b in codec.decode(serial) if b.token == TOK_PART]


def element_parts(codec, serial):
    """Element parts read straight off the bitstream (independent of describe)."""
    return [b.part.value for b in part_blocks(codec, serial)
            if b.part.subtype == SUBTYPE_INT and b.part.index == 1 and b.part.value in ELEMENT_PARTS]


def norm(label):
    return vocab.normalize_element(label) if label else None


def ref_tuple(p):
    return (p.token_index, p.category_id, p.index, p.raw, p.name, p.category_link)


def info_mismatches(info, d):
    """Every way an ItemInfo differs from the legacy describe() dict (element compared normalised)."""
    bad = []

    def chk(name, got, want):
        if got != want:
            bad.append("%s: %r != legacy %r" % (name, got, want))

    chk("category_id", info.category_id, d["category_id"])
    chk("category", info.category, d["category"])
    chk("level", info.level, d["level"])
    chk("rarity", info.rarity, d["rarity"])
    chk("element", info.element, norm(d["element"]))
    chk("legendary_name", info.legendary_name, d["legendary_name"])
    chk("display_name", info.display_name, d["display_name"])
    chk("parts", [ref_tuple(p) for p in info.parts], [ref_tuple(p) for p in d["parts"]])
    chk("part labels", [p.label() for p in info.parts], [p.label() for p in d["parts"]])
    chk("other_components", list(info.other_components),
        [(c["rarity"], c["name"]) for c in d.get("other_components", [])])
    chk("tokens", info.tokens, d["tokens"])
    chk("content_pack", info.content_pack, d.get("content_pack", "coregame"))
    chk("content_pack_label", info.content_pack_label, d.get("content_pack_label", "Base game"))
    chk("owned", info.owned, d.get("owned", True))
    chk("manifest_ok", info.manifest_ok, d["manifest"])
    chk("warnings", list(info.warnings), d["warnings"])
    return bad


def assert_no_mismatches(pairs, limit=5):
    """pairs: iterable of (label, [mismatch strings]). Fails with the first few offenders."""
    offenders = [(label, bad) for label, bad in pairs if bad]
    assert not offenders, "%d mismatches, first: %s" % (len(offenders), offenders[:limit])


class Raises:
    """`with Raises(SerialError):` that also insists NOTHING broader than a ForgeError escapes."""
    def __init__(self, kind=SerialError):
        self.kind = kind

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError("expected %s, nothing raised" % self.kind.__name__)
        if not issubclass(et, self.kind):
            raise AssertionError("expected %s, got %s: %s" % (self.kind.__name__, et.__name__, ev))
        return True


def make_stub_rules(owned, label=lambda p: p, boom=None):
    """A RulesPort that keeps its own owned set (so two Forges can differ) and reads pack tags from data."""
    class StubRules(Module):
        name = "rules"
        purpose = "test stub"
        requires = ("data",)
        port = RulesPort

        def owned_packs(self):
            return frozenset(owned)

        def pack_label(self, pack):
            if boom:
                raise boom
            return label(pack)

        def pack_of(self, category_id, index):
            return self.dep("data").part_meta(category_id, index).get("pack") or "coregame"

        def is_owned(self, category_id, index):
            return self.pack_of(category_id, index) in owned

        def serial_ownership(self, serial):
            return True, None

        def validate(self, serial):
            return []
    return StubRules


# ---- module identity ------------------------------------------------------------------------------

def test_module_identity_and_port_conformance(ops):
    assert MODULE is OpsModule
    assert (OpsModule.name, OpsModule.requires, OpsModule.port) == ("ops", ("codec", "data", "rules"), OpsPort)
    assert OpsModule.purpose == "Understand and modify one serial: identify, element, seed, part swap, diff."
    assert conformance_problems(ops, OpsPort) == []
    assert isinstance(ops, OpsPort)


def test_doctor_state_is_ok(forge):
    st = forge.states["ops"]
    assert st.state == "ok", st.detail
    assert [c.name for c in st.health.checks if not c.ok] == []


def test_sees_only_declared_neighbours():
    """Never import another module's package; reach neighbours only through self.dep()."""
    for path in sorted(OPS_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                target = "." * node.level + (node.module or "")
                names = [a.name for a in node.names]
                if node.level >= 2 and (node.module or "").split(".")[0] == "modules":
                    pytest.fail("%s imports another module package: %s" % (path.name, target))
                if node.level == 3 and not (node.module or "").startswith("core"):
                    pytest.fail("%s imports outside core/: %s %s" % (path.name, target, names))
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert not a.name.startswith("bl4forge.modules"), "%s imports %s" % (path.name, a.name)
    src = (OPS_DIR / "__init__.py").read_text(encoding="utf-8")
    for dep in ('dep("codec")', 'dep("data")', 'dep("rules")'):
        assert dep in src


# ---- CONTRACT invariants ------------------------------------------------------------------------------

def test_bitstream_is_authoritative(ops, codec, legacy):
    """describe() takes a serial and nothing else: a wrong database label cannot reach it."""
    rows = [e for e in legacy.forge.load_db() if e.get("type") == "weapon"]
    liars = []
    for e in rows:
        label = e.get("bulletType")
        if not label:
            continue
        try:
            claimed = vocab.normalize_element(label)
        except ValueError:
            continue
        found = element_parts(codec, e["serial"])            # the bitstream's own answer
        truth = ELEMENT_PARTS[found[-1]] if found else "impact"
        if claimed != truth:
            liars.append((e["serial"], claimed, truth))
    assert len(liars) > 50, "expected the known ~3% of mislabelled database rows, found %d" % len(liars)
    for serial, claimed, truth in liars:
        assert ops.describe(serial).element == truth != claimed
    # the label is not even an input, and the module never opens the database
    assert list(inspect.signature(ops.describe).parameters) == ["serial"]
    for path in OPS_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "serial_db_path" not in text and "open(" not in text, path.name


def test_pearl_rarity_from_meta(ops, data, codec, legacy, synthetic):
    """A comp_05_legendary_* part tagged Pearl in part_meta describes as Pearl (real parts, real tags)."""
    meta = legacy.partsdb.part_meta()
    pearls = {k: v for k, v in meta.items() if v.get("rarity") == "Pearl"}
    assert len(pearls) >= 15
    lookup = dict(synthetic)
    named_legendary = 0
    for key, entry in sorted(pearls.items()):
        cat, idx = (int(x) for x in key.split(":"))
        raw = data.part_table(cat)[idx]
        serial = lookup.get("replace %s %s" % (key, entry["name"]))
        assert serial, "no database serial to build the %s pearlescent (%s) from" % (entry["name"], key)
        info = ops.describe(serial)
        assert info.rarity == "Pearl", (key, entry["name"], info.rarity)
        assert info.legendary_name == entry["name"] and info.display_name == entry["name"]
        comp = [p for p in info.parts if p.index == idx and p.category_id == cat][0]
        assert comp.raw == raw and comp.name == "Pearl %s %s" % (DASH, entry["name"])
        if "legendary" in raw:
            named_legendary += 1
            # the NAME says legendary - both the raw string and the data module's display label
            assert ops_pkg._comp_info(raw)[0] == "Legendary"
            assert data.prettify_part(raw).startswith("Legendary")
    assert named_legendary >= 10          # docs: 14 of the 20 pearlescents


def test_rarity_follows_part_meta_not_the_name(config, codec, data, ops, synthetic):
    """Same raw part name, different part_meta tag => different rarity: the name is never parsed."""
    key, serial = next((k, s) for k, s in synthetic if k.startswith("replace 26:84"))
    assert ops.describe(serial).rarity == "Pearl"

    class RetaggedData:
        def __getattr__(self, attr):
            return getattr(data, attr)

        def part_meta(self, category_id, index):
            if (category_id, index) == (26, 84):
                return {"rarity": "Epic", "name": "Retagged"}
            return data.part_meta(category_id, index)

    other = OpsModule(ModuleContext("ops", config, {"codec": codec, "data": RetaggedData(), "rules": ops.dep("rules")}))
    info = other.describe(serial)
    assert (info.rarity, info.legendary_name) == ("Epic", "Retagged")


def test_highest_tier_governs_and_others_reported(ops, data, codec, legacy, synthetic, by_category, info_by):
    """A pearlescent carrying a second, lower composition part: Pearl governs, the rest are reported."""
    meta = legacy.partsdb.part_meta()
    checked = 0
    for key, entry in sorted(meta.items()):
        if entry.get("rarity") != "Pearl":
            continue
        cat, idx = (int(x) for x in key.split(":"))
        table = data.part_table(cat)
        lower = [(i, n) for i, n in sorted(table.items())
                 if n.startswith("comp_") and i != idx and meta.get("%d:%d" % (cat, i), {}).get("rarity") in ("Legendary", "Epic")]
        if cat not in by_category or not lower:
            continue
        low_idx, low_raw = lower[0]
        low_meta = meta["%d:%d" % (cat, low_idx)]
        base = next(s for k, s in synthetic if k == "replace %s %s" % (key, entry["name"]))
        for order, serial in (("pearl first", append_part(codec, base, low_idx)),
                              ("pearl last", None)):
            if serial is None:
                # put the lower component FIRST and the pearl later: stream order must not matter
                b = codec.decode(base)
                first = next(i for i, x in enumerate(b) if x.token == TOK_PART)
                low = Block(TOK_PART, part=Part(index=low_idx))
                serial = codec.encode(b[:first] + (low,) + b[first:])
            info = ops.describe(serial)
            assert info.rarity == "Pearl", (key, order)
            assert info.legendary_name == entry["name"], (key, order)
            assert len(info.other_components) >= 1
            assert info.other_components[0][0] == low_meta["rarity"], (key, order, info.other_components)
            assert all(vocab.RARITY_RANK[r] <= vocab.RARITY_RANK["Pearl"] for r, _ in info.other_components)
            assert not info_mismatches(info, legacy.partsdb.describe(serial))
        checked += 1
    assert checked >= 10
    # and the embedded known answer: Solar Temper (Pearl) + Fisheye (Legendary)
    pearl2 = ops.describe(_known.KNOWN[3][1])
    assert pearl2.rarity == "Pearl" and pearl2.other_components == (("Legendary", "Fisheye"),)
    # ordinary single-component items report none
    assert all(not i.other_components for i in (ops.describe(s) for s in (_known.KNOWN[0][1], _known.KNOWN[1][1])))


def test_set_element_round_trips(ops, codec, weapons):
    """Setting an item to its own element returns the identical serial; 'impact' strips the part."""
    assert len(weapons) > 2000
    with_part = 0
    for s in weapons:
        found = element_parts(codec, s)
        assert len(found) <= 1                          # the database has no double-element weapon
        info = ops.describe(s)
        assert info.element == (ELEMENT_PARTS[found[0]] if found else "impact")
        assert ops.set_element(s, info.element) == s, s                 # own element: identical serial
        stripped = ops.set_element(s, "impact")
        assert element_parts(codec, stripped) == []                     # the part is gone ...
        assert ops.describe(stripped).element == "impact"               # ... and it reads as impact
        if found:
            with_part += 1
            assert stripped != s
            assert ops.set_element(stripped, info.element) != stripped  # and it can be put back
        else:
            assert stripped == s                                        # already plain: nothing to strip
    assert with_part > 1000


def test_set_element_is_idempotent_and_changes_only_the_element(ops, codec, weapons):
    rng = random.Random(7)
    for s in rng.sample(weapons, 300):
        for element in SCALE_ELEMENTS:
            once = ops.set_element(s, element)
            assert ops.set_element(once, element) == once
            a, b = ops.describe(s), ops.describe(once)
            assert b.element == element
            assert (a.category_id, a.level, a.rarity, a.legendary_name) == (b.category_id, b.level, b.rarity, b.legendary_name)
            assert ops.get_seed(once) == ops.get_seed(s)


def test_swap_refuses_cross_category(ops, legacy, by_category, info_by):
    cats = sorted(c for c in by_category if c is not None)
    pairs = [(by_category[a][0], by_category[b][0]) for a, b in zip(cats, cats[1:])][:60]
    assert len(pairs) == 60
    for base, source in pairs:
        with pytest.raises(SerialError) as caught:
            ops.swap_parts(base, source, [0])
        msg = str(caught.value)
        assert "refusing to swap between different item categories" in msg
        assert info_by[base].category in msg and info_by[source].category in msg     # names both sides
        with pytest.raises(ValueError):                                              # legacy refuses too
            legacy.partsdb.swap_parts(base, source, [0])
        # the explicit opt-in goes through, and equals legacy's opt-in
        assert ops.swap_parts(base, source, [0], allow_cross=True) == \
            legacy.partsdb.swap_parts(base, source, [0], True)
    # same category is never refused
    a, b = by_category[cats[0]][0], by_category[cats[0]][-1]
    assert isinstance(ops.swap_parts(a, b, [0]), str)


def test_gear_has_no_element(ops, data, distinct, info_by):
    """Shields, class mods, repair kits and enhancements never report an element; weapons always do."""
    kinds = {"shield": 0, "class mod": 0, "repair kit": 0, "enhancement": 0}
    for s in distinct:
        info = info_by[s]
        name = (info.category or "").lower()
        for k in kinds:
            if k in name:
                kinds[k] += 1
                assert info.element is None, (s, info.category, info.element)
        assert (info.element is not None) == data.is_weapon_category(info.category_id), (s, info.category)
        if info.element is not None:
            assert info.element in vocab.ELEMENTS
    assert all(n > 50 for n in kinds.values()), kinds
    # swapping an element onto gear is a caller decision (legacy parity), but describe still says None
    # for the untouched item and the helper never invents one
    shield = _known.KNOWN[1][1]
    assert ops.describe(shield).element is None


def _last(ops, base, source):
    """The SerialError a cross-category swap raises."""
    try:
        ops.swap_parts(base, source, [0])
    except SerialError as ex:
        return ex
    raise AssertionError("not refused")


def test_describe_never_raises_without_manifest(config, legacy, tmp_path, all_serials):
    """Empty data dir: manifest_ok False plus a warning, still a typed ItemInfo with the decoded basics."""
    cfg = dataclasses.replace(config, data_dir=tmp_path)
    forge = Forge.build(cfg, overrides={"rules": LegacyRules(legacy, config)})
    assert forge.states["data"].state != "ok"
    ops = forge.ops
    for s in all_serials[:200]:
        info = ops.describe(s)
        assert isinstance(info, ItemInfo) and info.serial == s
        assert info.manifest_ok is False and info.warnings and "manifest" in info.warnings[0]
        assert info.category_id is not None and info.level is not None and info.tokens
        assert info.category is None and info.parts == () and info.rarity is None and info.element is None
        assert info.owned is True and info.content_pack == "coregame"
    s = all_serials[0]
    # every other operation degrades instead of raising ForgeError for the missing manifest
    assert ops.part_list(s) == []
    est = ops.rarity_estimate(ops.describe(s))
    assert est["tier_odds"] is None and est["sources"] == [] and est["dedicated_tier_rates"] == {}
    assert ops.format_odds(est) == ""
    assert isinstance(ops.set_seed(s, 9), str) and ops.get_seed(s) is not None
    assert ops.diff(s, all_serials[1]) is not None
    other = next(x for x in all_serials if ops.describe(x).category_id != ops.describe(s).category_id)
    with Raises(SerialError):
        ops.swap_parts(s, other, [0])
    assert "?" in str(_last(ops, s, other))        # category names unknown: shown as '?', not a crash


def test_matches_legacy(ops, all_serials, infos, legacy_infos, config):
    """All 9,875 serials: category_id, level, rarity, names, parts, owned, pack, warnings equal legacy."""
    assert len(all_serials) == len(infos) == len(legacy_infos) == 9875
    assert_no_mismatches((s, info_mismatches(i, d)) for s, i, d in zip(all_serials, infos, legacy_infos))
    for s, i in zip(all_serials, infos):
        assert isinstance(i, ItemInfo) and i.serial == s and i.manifest_ok
        assert all(isinstance(p, PartRef) for p in i.parts)
        assert i.element is None or i.element in vocab.ELEMENTS      # vocab names, not legacy labels
    # the 62 database items with no composition part are described, not rejected
    assert sum(1 for i in infos if i.rarity is None) == 62


def test_matches_legacy_on_pearls_packs_and_ownership(ops, synthetic, legacy):
    """Items the database does not contain: pearlescents, other_components, unowned content."""
    assert len(synthetic) >= 130
    results = [(label, info_mismatches(ops.describe(s), legacy.partsdb.describe(s))) for label, s in synthetic]
    assert_no_mismatches(results)
    infos = [ops.describe(s) for _, s in synthetic]
    assert any(i.owned is False and i.content_pack == "story_pack_1" for i in infos)
    assert any(i.owned is True and i.content_pack.startswith("bounty_pack") for i in infos)
    unowned = [i for i in infos if not i.owned][0]
    assert unowned.warnings[0].startswith("requires ") and unowned.content_pack_label in unowned.warnings[0]
    assert any(i.other_components for i in infos)


def test_odds_are_base_rates(ops, all_serials, infos, synthetic):
    """Numbers are labelled as world-drop base rates ('~'); a boss with no rate gets no percentage."""
    saw_unrated_boss = saw_world = 0
    for s, i in zip(all_serials, infos):
        est = ops.rarity_estimate(i)
        text = ops.format_odds(est)
        bosses = [x for x in est["sources"] if x["source_type"] == "Boss"]
        if est["item_odds"] or est["tier_odds"]:
            assert "~1 in" in text and "exact" not in text.lower()
            saw_world += 1
        if bosses and not any(b.get("chance") for b in bosses):
            saw_unrated_boss += 1
            assert "%" not in text, (s, text)
            for b in bosses[:3]:
                assert str(b["source"]) in text
    assert saw_world > 1000 and saw_unrated_boss > 100
    # the data module hands over the published tier table; we pass it through, never computing bosses from it
    assert ops.rarity_estimate(infos[0])["dedicated_tier_rates"] == ops.dep("data").drops().get("probabilities")
    # no world-drop weight exists for Pearl/Vile: no invented odds
    pearl = ops.describe(_known.KNOWN[2][1])
    est = ops.rarity_estimate(pearl)
    assert est["rarity"] == "Pearl" and est["tier_odds"] is None and est["item_odds"] is None
    assert "world drop" not in ops.format_odds(est)
    # weights are the published ones and sum to the published total
    assert abs(sum(_odds.RARITY_WEIGHTS.values()) - _odds.RARITY_WEIGHT_TOTAL) < 1e-9


def test_format_odds_wording(ops):
    """Hand-made estimates: what it may and may not say."""
    base = {"rarity": "Legendary", "tier_odds": None, "item_odds": None, "sources": []}
    assert ops.format_odds(base) == ""
    tier = dict(base, tier_odds={"probability": 1.0, "one_in": 353951})
    assert ops.format_odds(tier) == "any legendary world drop ~1 in 353,951"
    item = dict(tier, item_odds={"probability": 1.0, "one_in": 7000})
    assert ops.format_odds(item) == "world drop ~1 in 7,000"           # the item number wins, still a '~'

    def boss(source, chance=None, tier=None):
        return {"source": source, "source_type": "Boss", "tier": tier, "chance": chance, "pool": None}

    assert ops.format_odds(dict(base, sources=[boss("Mimicron")])) == "dedicated: Mimicron"
    assert ops.format_odds(dict(base, sources=[boss("Mimicron", tier="Primary")])) == "Mimicron (primary)"
    assert ops.format_odds(dict(base, sources=[boss("Mimicron", chance=0.0625)])) == "Mimicron 6.2%"
    many = dict(base, sources=[boss("A"), boss("B"), boss("C"), boss("D"), boss("E")])
    assert ops.format_odds(many) == "dedicated: A · dedicated: B · dedicated: C · +2 more sources"
    assert "%" not in ops.format_odds(many)


# ---- parity: odds ---------------------------------------------------------------------------------

def test_rarity_estimate_and_format_odds_match_legacy(ops, legacy, all_serials, infos, legacy_infos, synthetic):
    bad = []
    pairs = list(zip(all_serials, infos, legacy_infos))
    pairs += [(s, ops.describe(s), legacy.partsdb.describe(s)) for _, s in synthetic]
    shown = 0
    for s, info, d in pairs:
        want = legacy.partsdb.rarity_estimate(d)
        got = ops.rarity_estimate(info)
        if dict(got) != want:
            bad.append((s, "estimate"))
        elif ops.format_odds(got) != legacy.partsdb.format_odds(want):
            bad.append((s, "text"))
        shown += bool(want["sources"])
    assert not bad, bad[:5]
    assert shown > 500                      # the sweep really exercised items with drop sources


def test_rarity_estimate_is_a_plain_copy(ops, infos):
    est = ops.rarity_estimate(infos[0])
    assert isinstance(est, dict)
    est["tier_odds"] = "scribble"
    est["dedicated_tier_rates"]["scribble"] = 1
    again = ops.rarity_estimate(infos[0])
    assert again["tier_odds"] != "scribble" and "scribble" not in again["dedicated_tier_rates"]


# ---- parity: element ---------------------------------------------------------------------------------

def test_set_element_matches_legacy_for_every_weapon_and_element(ops, legacy, weapons):
    bad = []
    for s in weapons:
        for element in SCALE_ELEMENTS:
            # legacy takes 'impact' and the display names; ours takes vocab names - same set
            want = legacy.partsdb.set_element(s, element)
            got = ops.set_element(s, element)
            if got != want:
                bad.append((s, element))
    assert not bad, bad[:5]


def test_set_element_aliases_and_errors(ops, legacy, weapons):
    s = weapons[0]
    for alias in ("Electric", "ICE", " lightning ", "rad", "acid", "burn", "corrosion", "none", "kinetic", "physical", "", None):
        assert ops.set_element(s, alias) == legacy.partsdb.set_element(s, alias), alias
    for alias, canonical in (("electric", "shock"), ("ice", "cryo"), ("none", "impact"), (None, "impact")):
        assert ops.set_element(s, alias) == ops.set_element(s, canonical)
    for bad in ("plasma", "fire!", 42):
        with Raises(SerialError):
            ops.set_element(s, bad)
    with Raises(SerialError):
        ops.set_element("not a serial", "fire")


def test_set_element_on_gear_follows_legacy(ops, legacy, distinct, info_by):
    """Not refused (legacy parity): gear gets the part if asked. describe() on the untouched item stays None."""
    gear = [s for s in distinct if info_by[s].element is None][:60]
    for s in gear:
        assert ops.set_element(s, "fire") == legacy.partsdb.set_element(s, "fire")
        assert ops.set_element(s, "impact") == legacy.partsdb.set_element(s, "impact") == s


# ---- parity: seed -----------------------------------------------------------------------------------

def test_get_seed_matches_legacy_for_every_serial(ops, legacy, all_serials):
    assert [ops.get_seed(s) for s in all_serials] == [legacy.partsdb.get_seed(s) for s in all_serials]
    assert all(isinstance(ops.get_seed(s), int) for s in all_serials[:50])


def test_set_seed_matches_legacy_and_changes_only_the_seed(ops, codec, legacy, distinct, info_by):
    rng = random.Random(11)
    sample = rng.sample(distinct, 500)
    for s in sample:
        for seed in (0, 1, rng.randrange(0, 4096), 4095, 65535):
            got = ops.set_seed(s, seed)
            assert got == legacy.partsdb.set_seed(s, seed)
            assert ops.get_seed(got) == seed
        a, b = info_by[s], ops.describe(ops.set_seed(s, 777))
        assert (a.category_id, a.level, a.rarity, a.element, a.legendary_name) == \
               (b.category_id, b.level, b.rarity, b.element, b.legendary_name)
        assert [ref_tuple(p) for p in a.parts] == [ref_tuple(p) for p in b.parts]
        assert ops.set_seed(s, ops.get_seed(s)) == s                # re-storing the same seed is a no-op


def test_seed_beyond_legacy_limits_and_bad_values(ops, distinct):
    s = distinct[0]
    # legacy silently truncated anything above 65535 to a different number; we store it exactly
    assert ops.get_seed(ops.set_seed(s, 70000)) == 70000
    assert ops.get_seed(ops.set_seed(s, 2 ** 31 - 1)) == 2 ** 31 - 1
    for bad in (-1, 2 ** 31, 2 ** 32 - 1, "7", 1.5, True, None):
        with Raises(SerialError):
            ops.set_seed(s, bad)


def test_serial_without_a_seed(ops, codec):
    short = codec.encode(codec.from_string("3, 0, 1, 50|"))
    assert ops.get_seed(short) is None
    with Raises(SerialError):
        ops.set_seed(short, 5)
    info = ops.describe(short)                      # still identifiable
    assert (info.category_id, info.level, info.parts) == (3, 50, ())


# ---- parity: swap -------------------------------------------------------------------------------------

def _pair_cases(rng, by_category, legacy_by, n):
    multi = [c for c, v in sorted(by_category.items(), key=lambda kv: str(kv[0])) if len(v) >= 2]
    cases = []
    while len(cases) < n:
        cat = rng.choice(multi)
        a, b = rng.sample(by_category[cat], 2)
        room = min(len(legacy_by[a]["parts"]), len(legacy_by[b]["parts"]))
        if room < 1:
            continue
        k = rng.randint(1, min(3, room))
        cases.append((a, b, rng.sample(range(room), k)))
    return cases


def test_swap_parts_matches_legacy_on_same_category_pairs(ops, codec, legacy, by_category, legacy_by, info_by):
    rng = random.Random(23)
    cases = _pair_cases(rng, by_category, legacy_by, 400)
    for base, source, positions in cases:
        got = ops.swap_parts(base, source, positions)
        assert got == legacy.partsdb.swap_parts(base, source, positions), (base, source, positions)
        # semantics: swapped positions carry the source's part, every other position keeps the base's
        out_parts = [b.part for b in part_blocks(codec, got)]
        base_parts = [b.part for b in part_blocks(codec, base)]
        src_parts = [b.part for b in part_blocks(codec, source)]
        for i, part in enumerate(out_parts):
            assert part == (src_parts[i] if i in positions else base_parts[i])
        # nothing but parts changed: header, level, seed, separators, strings
        non_part = lambda s: [b for b in codec.decode(s) if b.token != TOK_PART]
        assert non_part(got) == non_part(base)


def test_swap_positions_count_part_blocks_not_tokens(ops, codec, by_category, distinct, info_by):
    s = next(x for x in distinct if len(info_by[x].parts) > 3)
    refs = ops.part_list(s)
    assert all(r.token_index > k for k, r in enumerate(refs))         # header tokens come first
    donor = by_category[info_by[s].category_id][-1]
    got = ops.swap_parts(s, donor, [2])
    assert got == ops.swap_parts(s, donor, [2], allow_cross=False)
    new = codec.decode(got)
    old = codec.decode(s)
    changed = [i for i, (x, y) in enumerate(zip(old, new)) if x != y]
    assert changed in ([], [refs[2].token_index])                    # position 2 -> token index of part 2


def test_swap_parts_error_cases_match_legacy(ops, legacy, by_category, legacy_by):
    rng = random.Random(29)
    for base, source, positions in _pair_cases(rng, by_category, legacy_by, 40):
        room = min(len(legacy_by[base]["parts"]), len(legacy_by[source]["parts"]))
        for bad in ([-1], [room + 50], positions + [10 ** 6]):
            with pytest.raises(ValueError):
                legacy.partsdb.swap_parts(base, source, bad)
            with Raises(SerialError):
                ops.swap_parts(base, source, bad)
        # an empty swap is just a re-encode
        assert ops.swap_parts(base, source, []) == legacy.partsdb.swap_parts(base, source, []) == base
    with Raises(SerialError):
        ops.swap_parts(base, source, "01")
    with Raises(SerialError):
        ops.swap_parts(base, source, [True])
    with Raises(SerialError):
        ops.swap_parts(base, source, 3)
    with Raises(SerialError):
        ops.swap_parts(base, source, ["a"])


def test_swap_parts_cross_category_matches_legacy(ops, legacy, by_category, legacy_by):
    cats = sorted(c for c in by_category if c is not None)
    rng = random.Random(31)
    for _ in range(80):
        ca, cb = rng.sample(cats, 2)
        a, b = rng.choice(by_category[ca]), rng.choice(by_category[cb])
        room = min(len(legacy_by[a]["parts"]), len(legacy_by[b]["parts"]))
        if room < 1:
            continue
        positions = rng.sample(range(room), min(2, room))
        with Raises(SerialError):
            ops.swap_parts(a, b, positions)
        assert ops.swap_parts(a, b, positions, allow_cross=True) == legacy.partsdb.swap_parts(a, b, positions, True)


# ---- parity: diff, part_list ---------------------------------------------------------------------------------

def _legacy_diff(legacy, a, b):
    rows = legacy.partsdb.diff(a, b)
    for row in rows:
        if row["field"] == "element":
            row["a"], row["b"] = norm(row["a"]), norm(row["b"])
    return rows


def test_diff_matches_legacy(ops, legacy, by_category, legacy_by, distinct, synthetic):
    rng = random.Random(37)
    pairs = [(a, b) for a, b, _ in _pair_cases(rng, by_category, legacy_by, 250)]
    pairs += [tuple(rng.sample(distinct, 2)) for _ in range(150)]
    pairs += [(rng.choice(distinct), s) for _, s in synthetic[:40]]
    nonempty = 0
    for a, b in pairs:
        got = ops.diff(a, b)
        assert got == _legacy_diff(legacy, a, b), (a, b)
        nonempty += bool(got)
    assert nonempty > 300
    assert all(ops.diff(s, s) == [] for s in distinct[:100])


def test_diff_reports_fields_and_parts(ops, distinct):
    weapon = _known.KNOWN[0][1]
    rows = ops.diff(weapon, ops.set_element(weapon, "cryo"))
    fields = {r["field"] for r in rows}
    assert "element" in fields
    assert {"field": "element", "a": "shock", "b": "cryo"} in rows
    assert ops.diff(weapon, ops.set_seed(weapon, 3)) == []         # the seed is not a part or header field shown
    rows = ops.diff(weapon, _known.KNOWN[1][1])
    assert {"category", "legendary_name"} <= {r["field"] for r in rows}


def test_part_list_matches_legacy(ops, legacy, all_serials):
    for s in all_serials[::7]:
        got = ops.part_list(s)
        want = legacy.partsdb.part_list(s)
        assert isinstance(got, list) and all(isinstance(p, PartRef) for p in got)
        assert [ref_tuple(p) for p in got] == [ref_tuple(p) for p in want]
        assert [p.label() for p in got] == [p.label() for p in want]


# ---- purity, state, errors -------------------------------------------------------------------------------------

def test_no_module_level_mutable_state():
    """Constants only: no `global`, no mutable literals/containers at module level in any ops file."""
    mutable = (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
    safe_calls = {"MappingProxyType", "frozenset", "tuple", "compile", "getLogger"}
    for path in sorted(OPS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.Global)], path.name
        for node in tree.body:
            value = getattr(node, "value", None) if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
            if value is None:
                continue
            assert not isinstance(value, mutable), "%s:%d mutable module-level value" % (path.name, node.lineno)
            if isinstance(value, ast.Call):
                fn = value.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                assert name in safe_calls, "%s:%d module-level call %s()" % (path.name, node.lineno, name)


def test_two_forges_do_not_interfere(config, legacy, synthetic):
    """Different owned-pack sets, different Forge instances, same process: each answers for itself."""
    sharkbait = next(s for k, s in synthetic if k.startswith("replace 11:90"))        # story_pack_1
    default = Forge.build(config, overrides={"rules": make_stub_rules(config.owned_packs)})
    generous = Forge.build(config, overrides={"rules": make_stub_rules(config.owned_packs + ("story_pack_1",))})
    for _ in range(2):                                            # interleave: no shared state to leak
        a, b = default.ops.describe(sharkbait), generous.ops.describe(sharkbait)
        assert (a.owned, b.owned) == (False, True)
        assert a.content_pack == b.content_pack == "story_pack_1"
        assert a.warnings and not b.warnings
    assert default.ops is not generous.ops


def test_transforms_return_new_serials_and_leave_inputs_alone(ops, codec, distinct, weapons):
    rng = random.Random(41)
    for s in rng.sample(weapons, 100):
        before = codec.decode(s)
        other = rng.choice(distinct)
        outs = [ops.set_element(s, "fire"), ops.set_element(s, None), ops.set_seed(s, 123),
                ops.swap_parts(s, s, [0, 1]), ops.swap_parts(s, s, [])]
        assert all(isinstance(o, str) and o.startswith("@U") for o in outs)
        assert codec.decode(s) == before
        for o in outs:
            codec.decode(o)                                         # every result is a valid serial
        lvl = codec.get_level(before)
        assert all(codec.get_level(codec.decode(o)) == lvl for o in outs)
        assert all(codec.get_category_id(codec.decode(o)) == codec.get_category_id(before) for o in outs)
        ops.diff(s, other)
        ops.describe(s)
        assert codec.decode(s) == before


GARBAGE = ("", "@U", "not a serial", "@Ug" + "!" * 5, None, 123, b"@Ug", ["@Ug"])


@pytest.mark.parametrize("bad", GARBAGE, ids=lambda v: repr(v)[:20])
def test_errors_are_serialerror(ops, distinct, bad):
    good = distinct[0]
    calls = [
        lambda: ops.describe(bad), lambda: ops.part_list(bad), lambda: ops.get_seed(bad),
        lambda: ops.set_seed(bad, 1), lambda: ops.set_element(bad, "fire"),
        lambda: ops.swap_parts(bad, good, [0]), lambda: ops.swap_parts(good, bad, [0]),
        lambda: ops.diff(bad, good), lambda: ops.diff(good, bad),
    ]
    for call in calls:
        with Raises(SerialError):
            call()
    assert issubclass(SerialError, ForgeError)


# ---- health ---------------------------------------------------------------------------------------------

def test_health_known_answers(ops):
    report = ops.health()
    assert isinstance(report, HealthReport) and report.ok, report
    names = [c.name for c in report.checks]
    assert any("weapon" in n for n in names) and any("shield" in n for n in names) \
        and sum("pearlescent" in n for n in names) == 2 and "transforms" in names
    assert all(c.ok for c in report.checks)


def test_embedded_known_serials_match_legacy(legacy, ops):
    for label, serial, cat, level, rarity, element, name, seed, others in _known.KNOWN:
        d = legacy.partsdb.describe(serial)
        assert (d["category_id"], d["level"], d["rarity"], norm(d["element"]), d["legendary_name"]) == \
               (cat, level, rarity, element, name), label
        assert legacy.partsdb.get_seed(serial) == seed, label
        assert tuple((c["rarity"], c["name"]) for c in d.get("other_components", [])) == tuple(others), label


def test_health_never_raises_and_reports_trouble(config, legacy, tmp_path):
    # a sick rules neighbour
    sick = Forge.build(config, overrides={"rules": make_stub_rules(config.owned_packs, boom=RuntimeError("rules down"))})
    report = sick.ops.health()
    assert not report.ok and "rules" in report.summary
    assert any(c.name == "rules-dependency" and not c.ok for c in report.checks)
    assert any(c.name == "transforms" and c.ok for c in report.checks)       # what does not need rules still passes
    # no manifest at all
    cfg = dataclasses.replace(config, data_dir=tmp_path)
    nodata = Forge.build(cfg, overrides={"rules": LegacyRules(legacy, config)})
    report = nodata.ops.health()
    assert not report.ok and any(c.name == "manifest" and not c.ok for c in report.checks)
    # the skeleton-style failure: every neighbour call raises something odd
    class Boom:
        def __getattr__(self, name):
            raise RuntimeError("boom " + name)
    wrecked = OpsModule(ModuleContext("ops", config, {"codec": Boom(), "data": Boom(), "rules": Boom()}))
    report = wrecked.health()
    assert isinstance(report, HealthReport) and not report.ok


# ---- real rules (re-run by the coordinator once `rules` has landed) -----------------------------------------------

def test_with_real_rules(config, legacy, all_serials, synthetic):
    """The same facts, with the real rules module instead of the legacy-backed double."""
    forge = Forge.build(config)
    if forge.states["rules"].state != "ok":
        pytest.skip("rules module is %s: %s" % (forge.states["rules"].state, forge.states["rules"].detail))
    legacy.partsdb.set_owned_packs(config.owned_packs)
    ops = forge.ops
    assert forge.states["ops"].state == "ok", forge.states["ops"].detail
    assert conformance_problems(ops, OpsPort) == []

    sample = all_serials[::3]
    assert_no_mismatches((s, info_mismatches(ops.describe(s), legacy.partsdb.describe(s))) for s in sample)
    assert_no_mismatches((l, info_mismatches(ops.describe(s), legacy.partsdb.describe(s))) for l, s in synthetic)

    unowned = ops.describe(next(s for k, s in synthetic if k.startswith("replace 11:90")))
    assert unowned.owned is False and unowned.content_pack == "story_pack_1" and unowned.rarity == "Pearl"
    assert ops.describe(next(s for k, s in synthetic if k.startswith("replace 20:70"))).owned is True

    # owned set comes from config through rules
    cfg2 = dataclasses.replace(config, owned_packs=config.owned_packs + ("story_pack_1",))
    forge2 = Forge.build(cfg2)
    sharkbait = next(s for k, s in synthetic if k.startswith("replace 11:90"))
    assert forge.ops.describe(sharkbait).owned is False and forge2.ops.describe(sharkbait).owned is True

    rng = random.Random(53)
    for s in rng.sample(all_serials, 150):
        assert ops.get_seed(s) == legacy.partsdb.get_seed(s)
        assert ops.set_seed(s, 321) == legacy.partsdb.set_seed(s, 321)
        assert ops.diff(s, all_serials[0]) == _legacy_diff(legacy, s, all_serials[0])
        assert ops.format_odds(ops.rarity_estimate(ops.describe(s))) == \
            legacy.partsdb.format_odds(legacy.partsdb.rarity_estimate(legacy.partsdb.describe(s)))
        if ops.describe(s).element is not None:
            for element in ("fire", "impact"):
                assert ops.set_element(s, element) == legacy.partsdb.set_element(s, element)
    assert ops.describe(_known.KNOWN[2][1]).rarity == "Pearl"
    assert ops.health().ok


# ---- relevel (added in coordinator change: builder needs it through ops, see CHANGE_REQUESTS.md) ----

def test_relevel_matches_legacy_codec(ops, legacy, all_serials):
    for s in all_serials[::25]:
        assert ops.relevel(s, 60) == legacy.codec.relevel(s, 60)
        assert ops.describe(ops.relevel(s, 60)).level == 60


def test_relevel_failure_is_serialerror_not_silent(ops, all_serials):
    with pytest.raises(SerialError):
        ops.relevel("not a serial", 60)
    with pytest.raises(SerialError):
        ops.relevel(all_serials[0], -1)
