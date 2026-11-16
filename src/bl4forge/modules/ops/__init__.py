"""ops: Understand and modify one serial: identify, element, seed, part swap, diff.

Everything here works on ONE serial at a time and trusts the decoded bitstream, never a database
label. The wire format is the codec's business, names/rarity/pack-tags are the data module's, and
ownership is the rules module's; this cell composes them. It keeps no state at all (no caches, no
module-level mutables), so two Forge instances cannot interfere. See CONTRACT.md in this directory.


DISCLOSURE (what this code does)
  Reads: nothing from disk. Writes: nothing. Network: none. Risk: none (pure computation on values passed in).
"""
from __future__ import annotations

import dataclasses
import re
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

from ...core import vocab
from ...core.errors import SerialError
from ...core.module import Module
from ...core.ports import OpsPort
from ...core.types import (
    Block, Blocks, HealthCheck, HealthReport, ItemInfo, Part, PartRef,
    SUBTYPE_INT, TOK_PART,
)
from . import _odds
from ._known import KNOWN

# The stat-variance seed is the 6th plain integer block of the header (legacy SEED_INT_POS). The
# codec counts integer blocks; WHICH position is the seed is item semantics, so ops owns the number.
SEED_POSITION = 5

# Elements live in the shared "Weapon" category (id 1) as bare `{1:N}` parts.
ELEMENT_CATEGORY = 1
ELEMENT_INDEX: Mapping[int, str] = MappingProxyType(
    {10: "corrosive", 11: "cryo", 12: "fire", 13: "radiation", 14: "shock"})
INDEX_BY_ELEMENT: Mapping[str, int] = MappingProxyType({v: k for k, v in ELEMENT_INDEX.items()})

# Legacy accepted "physical" for plain kinetic damage; vocab does not know that word.
_EXTRA_IMPACT_WORDS = ("physical",)

_COMP_RE = re.compile(r"^comp_(\d+)_([a-z]+)(?:_(.+))?$")
_DASH = "—"                  # the legacy display separator in "Legendary — Name"
_NO_MANIFEST = "manifest data not bundled — names unresolved"
_DEFAULT_PACK = "coregame"


def _comp_info(raw: Optional[str]) -> Optional[Tuple[str, Optional[str]]]:
    """`comp_05_legendary_hellwalker` -> ("Legendary", "hellwalker"); None if not a composition."""
    m = _COMP_RE.match(raw or "")
    if not m:
        return None
    tier = int(m.group(1))
    rarity = vocab.RARITIES[tier - 1] if 1 <= tier <= len(vocab.RARITIES) else m.group(2).capitalize()
    return rarity, m.group(3)


def _is_element_part(b: Block) -> bool:
    p = b.part
    return (b.token == TOK_PART and p is not None and p.subtype == SUBTYPE_INT
            and p.index == ELEMENT_CATEGORY and p.value in ELEMENT_INDEX)


def _element_index(element: Optional[str]) -> Optional[int]:
    """Element argument -> part index in category 1, or None meaning "strip the element part"."""
    key = "" if element is None else str(element).strip().lower()
    if key == "" or key in _EXTRA_IMPACT_WORDS:
        return None
    try:
        name = vocab.normalize_element(key)
    except ValueError as ex:
        raise SerialError("unknown element %r — use one of: %s" % (element, ", ".join(vocab.ELEMENTS))) from ex
    if name is None or name == "impact":
        return None
    return INDEX_BY_ELEMENT[name]


class OpsModule(Module):
    name = "ops"
    purpose = "Understand and modify one serial: identify, element, seed, part swap, diff."
    requires = ('codec', 'data', 'rules')
    port = OpsPort

    # ---- identify ----------------------------------------------------------------------------
    def describe(self, serial: str) -> ItemInfo:
        """Decode `serial` and resolve everything the manifest can say about it.

        Raises SerialError only for a serial that cannot be decoded. Missing manifest data never
        raises: the result has `manifest_ok=False` and a warning.
        """
        codec, data, rules = self.dep("codec"), self.dep("data"), self.dep("rules")
        blocks = codec.decode(serial)
        category_id = codec.get_category_id(blocks)
        level = codec.get_level(blocks)
        tokens = codec.parts_string(blocks)

        if not data.available():
            return ItemInfo(serial=serial, category_id=category_id, level=level, tokens=tokens,
                            manifest_ok=False, warnings=(_NO_MANIFEST,))

        names = data.category_names()
        category = names.get(category_id)
        own = data.part_table(category_id) if category_id is not None else {}

        refs: List[PartRef] = []
        comps: List[Tuple[int, str, Optional[str]]] = []      # (rank, rarity, name)
        packs_seen: Set[str] = set()
        all_owned = True
        element: Optional[str] = None

        for i, b in enumerate(blocks):
            if b.token != TOK_PART or b.part is None:
                continue
            p = b.part
            if p.subtype == SUBTYPE_INT:
                # {cat:index} - an index into another category's table.
                cat, idx = p.index, p.value
                raw = data.part_table(cat).get(idx)
            else:
                # {index} - an index into this item's own category table.
                cat, idx = category_id, p.index
                raw = own.get(idx)

            name = data.prettify_part(raw) if raw else None
            link: Optional[int] = None
            if raw is None and idx in names:
                # A plain {N} with no entry in the item's own table, where N is itself a category
                # id, is a cross-category pointer (the "firmware" parts: repair kit 243, shield 246,
                # enhancement 247, gadget 245, shield subtypes 237/248). Name it as what it points at.
                name = "%s (category link)" % names[idx]
                link = idx

            meta = data.part_meta(cat, idx)
            pack = rules.pack_of(cat, idx)
            if pack != _DEFAULT_PACK:
                packs_seen.add(pack)
                if not rules.is_owned(cat, idx):
                    all_owned = False

            # Relabel composition parts with the game's own rarity + display name.
            if raw and raw.startswith("comp_") and meta.get("rarity"):
                name = ("%s %s %s" % (meta["rarity"], _DASH, meta["name"])
                        if meta.get("name") else meta["rarity"])

            if raw:
                comp = _comp_info(raw)
                if comp:
                    # The game's explicit rarity field wins over the name string:
                    # `comp_05_legendary_temper` is tagged Pearl, not Legendary.
                    rarity = meta.get("rarity") or comp[0]
                    cname = meta.get("name") or (data.prettify_legendary(comp[1]) if comp[1] else None)
                    comps.append((vocab.RARITY_RANK.get(rarity, 0), rarity, cname))
                if cat == ELEMENT_CATEGORY and idx in ELEMENT_INDEX:
                    element = ELEMENT_INDEX[idx]

            refs.append(PartRef(token_index=i, category_id=cat, index=idx, raw=raw, name=name,
                                category_link=link))

        # An item can carry several composition parts (a pearlescent is often a named pearl
        # component plus a plain legendary one). The highest tier governs; the rest are reported.
        rarity_found: Optional[str] = None
        legendary_name: Optional[str] = None
        others: Tuple[Tuple[str, Optional[str]], ...] = ()
        if comps:
            comps.sort(key=lambda c: c[0], reverse=True)
            rarity_found = comps[0][1]
            for _, _, nm in comps:
                if nm:
                    legendary_name = nm
                    break
            others = tuple((r, n) for _, r, n in comps[1:])

        if element is None and data.is_weapon_category(category_id):
            # On a weapon, no element part means physical/impact damage. Gear has no element
            # concept at all, so it stays None.
            element = "impact"

        content_pack = sorted(packs_seen)[0] if packs_seen else _DEFAULT_PACK
        content_pack_label = rules.pack_label(content_pack)

        warnings: List[str] = []
        if not all_owned:
            warnings.append("requires %s, which is not in the owned-content set" % content_pack_label)
        unknown = sum(1 for r in refs if not r.raw and r.category_link is None)
        if unknown:
            warnings.append(
                "%d part index(es) not found in the manifest — the game may have been patched "
                "since this data was extracted" % unknown)

        return ItemInfo(
            serial=serial, category_id=category_id, category=category, level=level,
            rarity=rarity_found, element=element, legendary_name=legendary_name,
            display_name=legendary_name or category, parts=tuple(refs), other_components=others,
            tokens=tokens, content_pack=content_pack, content_pack_label=content_pack_label,
            owned=all_owned, manifest_ok=True, warnings=tuple(warnings))

    def part_list(self, serial: str) -> List[PartRef]:
        """Positional list of a serial's parts. (`swap_parts` positions count PART blocks, so
        position k is `part_list(serial)[k]`; `PartRef.token_index` indexes the raw Blocks.)"""
        return list(self.describe(serial).parts)

    # ---- drop odds ---------------------------------------------------------------------------
    def rarity_estimate(self, info: ItemInfo) -> Mapping[str, object]:
        """World-drop and dedicated-drop odds for a described item. BASE RATES only: luck and
        event modifiers are not in the data, so this is an estimate and is labelled as one."""
        data = self.dep("data")
        available = data.available()
        probabilities = data.drops().get("probabilities", {}) if available else {}
        return _odds.estimate(info.rarity, info.legendary_name, available, probabilities,
                              data.drops_by_item())

    def format_odds(self, estimate: Mapping[str, object]) -> str:
        """One-line summary of an estimate. Says nothing it cannot support: world-drop numbers
        carry '~', and dedicated sources with no rate in the data are named without a percentage."""
        return _odds.summarize(estimate)

    # ---- element -----------------------------------------------------------------------------
    def set_element(self, serial: str, element: Optional[str]) -> str:
        """New serial with its element part replaced, inserted, or removed.

        `None`, '' , 'impact' (and the aliases vocab knows: 'none', 'kinetic', ...) strip the
        element part, which is how the game represents plain kinetic damage. Setting an item to the
        element it already has returns the identical serial. Like legacy, this does not check that
        the item is a weapon.
        """
        codec = self.dep("codec")
        target = _element_index(element)
        blocks = tuple(codec.decode(serial))
        at = next((i for i, b in enumerate(blocks) if _is_element_part(b)), None)

        if target is None:
            if at is not None:
                blocks = blocks[:at] + blocks[at + 1:]
            return codec.encode(blocks)

        if at is not None:
            old = blocks[at]
            new = dataclasses.replace(old, part=dataclasses.replace(old.part, value=target))
            return codec.encode(blocks[:at] + (new,) + blocks[at + 1:])

        # No element part yet: insert one right after the last existing part, so it lands inside the
        # part list rather than in the header.
        last = None
        for i, b in enumerate(blocks):
            if b.token == TOK_PART:
                last = i
        if last is None:
            raise SerialError("serial has no part list to add an element to")
        new = Block(TOK_PART, part=Part(index=ELEMENT_CATEGORY, subtype=SUBTYPE_INT, value=target))
        return codec.encode(blocks[:last + 1] + (new,) + blocks[last + 1:])

    # ---- seed --------------------------------------------------------------------------------
    def get_seed(self, serial: str) -> Optional[int]:
        """The stat-variance seed, or None if the serial has no such field."""
        codec = self.dep("codec")
        return codec.int_at(codec.decode(serial), SEED_POSITION)

    def set_seed(self, serial: str, seed: int) -> str:
        """Reroll stat variance without touching parts or level. SerialError if the seed cannot be
        stored (not an int, negative, or above the codec's maximum) or the serial has no seed."""
        codec = self.dep("codec")
        blocks = codec.decode(serial)
        if codec.int_at(blocks, SEED_POSITION) is None:
            raise SerialError("could not locate the seed field in this serial")
        return codec.encode(codec.with_int_at(blocks, SEED_POSITION, seed))

    # ---- swap --------------------------------------------------------------------------------
    def relevel(self, serial: str, level: int) -> str:
        """Same item at a new level. The codec does the bit work; failures stay SerialError."""
        return self.dep("codec").relevel(serial, level)

    def swap_parts(self, base: str, source: str, positions: Sequence[int],
                   allow_cross: bool = False) -> str:
        """Copy the parts at `positions` from `source` into `base`.

        Positions are 0-based indexes among the PART blocks (as `part_list` shows), not token
        indexes. A bare `{N}` part indexes its own category's table, so the same number means
        different things on different items; swapping across categories is refused unless
        `allow_cross=True`. Finer part compatibility is NOT checked: a result has passed structural
        checks only, which is not the same as being valid in game.
        """
        codec, data = self.dep("codec"), self.dep("data")
        base_blocks = tuple(codec.decode(base))
        src_blocks = tuple(codec.decode(source))
        base_cat = codec.get_category_id(base_blocks)
        src_cat = codec.get_category_id(src_blocks)
        if base_cat != src_cat and not allow_cross:
            names = data.category_names()
            raise SerialError(
                "refusing to swap between different item categories: base is %s (%s), source is %s (%s). "
                "Plain part indices are category-relative, so the copied part would decode as something "
                "unrelated. Pass allow_cross=True only if you know the two categories share a parts table."
                % (names.get(base_cat, "?"), base_cat, names.get(src_cat, "?"), src_cat))

        if isinstance(positions, (str, bytes)):
            raise SerialError("positions must be a sequence of integers, got %r" % (positions,))
        try:
            wanted = list(positions)
        except TypeError as ex:
            raise SerialError("positions must be a sequence of integers, got %r" % (positions,)) from ex

        base_at = [i for i, b in enumerate(base_blocks) if b.token == TOK_PART]
        src_parts = [b.part for b in src_blocks if b.token == TOK_PART]
        out = list(base_blocks)
        for pos in wanted:
            if isinstance(pos, bool) or not isinstance(pos, int):
                raise SerialError("position %r is not an integer" % (pos,))
            if pos < 0 or pos >= len(src_parts):
                raise SerialError("position %d is out of range for the source serial (it has %d parts)"
                                  % (pos, len(src_parts)))
            if pos >= len(base_at):
                raise SerialError("position %d is out of range for the base serial (it has %d parts)"
                                  % (pos, len(base_at)))
            if src_parts[pos] is None:
                raise SerialError("source part %d is empty" % pos)
            at = base_at[pos]
            out[at] = dataclasses.replace(out[at], part=src_parts[pos])   # Part is frozen: safe to share
        return codec.encode(tuple(out))

    # ---- diff --------------------------------------------------------------------------------
    def diff(self, serial_a: str, serial_b: str) -> List[dict]:
        """Differences between two serials: header fields, then part-by-part labels. `element`
        values are vocab names ('shock', 'impact'), like everywhere else in the forge."""
        a, b = self.describe(serial_a), self.describe(serial_b)
        rows: List[dict] = []
        for field in ("category", "level", "rarity", "element", "legendary_name"):
            va, vb = getattr(a, field), getattr(b, field)
            if va != vb:
                rows.append({"field": field, "a": va, "b": vb})
        pa, pb = a.parts, b.parts
        for i in range(max(len(pa), len(pb))):
            la = pa[i].label() if i < len(pa) else None
            lb = pb[i].label() if i < len(pb) else None
            if la != lb:
                rows.append({"field": "part[%d]" % i, "a": la, "b": lb})
        return rows

    # ---- self-check --------------------------------------------------------------------------
    def health(self) -> HealthReport:
        """Known-answer checks on embedded serials. Never raises."""
        checks: List[HealthCheck] = []
        try:
            checks.extend(self._health_checks())
        except Exception as ex:      # health() must never raise
            checks.append(HealthCheck("health-run", False, "%s: %s" % (type(ex).__name__, ex)))
        bad = [c for c in checks if not c.ok]
        if not bad:
            summary = "%d known-answer checks passed" % len(checks)
        elif any(c.name == "rules-dependency" for c in bad):
            why = next(c.detail for c in bad if c.name == "rules-dependency")
            summary = "rules dependency not answering (%s); item checks not run" % why
        else:
            summary = "failed: " + ", ".join(c.name for c in bad)
        return HealthReport.from_checks(checks, summary)

    def _health_checks(self) -> List[HealthCheck]:
        checks: List[HealthCheck] = []
        manifest = self.dep("data").available()
        checks.append(HealthCheck("manifest", manifest,
                                  "available" if manifest else
                                  "no manifest data: describe() reports manifest_ok=False and no names"))
        try:
            self.dep("rules").pack_label(_DEFAULT_PACK)
            rules_ok, why = True, "answers"
        except Exception as ex:
            rules_ok, why = False, "%s: %s" % (type(ex).__name__, ex)
        checks.append(HealthCheck("rules-dependency", rules_ok, why))
        for row in KNOWN:
            if manifest and rules_ok:
                checks.append(self._check_known(*row))
            else:
                checks.append(HealthCheck("known-answer: " + row[0], False,
                                          "not run: " + ("rules dependency not answering" if manifest
                                                         else "manifest data not available")))
        checks.append(self._check_transforms())
        return checks

    def _check_known(self, label, serial, category_id, level, rarity, element, legendary_name,
                     seed, others) -> HealthCheck:
        name = "known-answer: " + label
        try:
            info = self.describe(serial)
            got = (info.category_id, info.level, info.rarity, info.element, info.legendary_name,
                   info.other_components, info.manifest_ok, info.owned)
            want = (category_id, level, rarity, element, legendary_name, tuple(others), True, True)
            if got != want:
                return HealthCheck(name, False, "got %r, expected %r" % (got, want))
            if self.get_seed(serial) != seed:
                return HealthCheck(name, False, "seed %r, expected %r" % (self.get_seed(serial), seed))
        except Exception as ex:
            return HealthCheck(name, False, "%s: %s" % (type(ex).__name__, ex))
        return HealthCheck(name, True, "%s %s, level %d" % (rarity, legendary_name, level))

    def _check_transforms(self) -> HealthCheck:
        """element / seed / swap behave on the embedded weapon, shield and pearlescent."""
        name = "transforms"
        try:
            weapon, shield, pearl = KNOWN[0][1], KNOWN[1][1], KNOWN[2][1]
            if self.set_element(weapon, "shock") != weapon:
                return HealthCheck(name, False, "set_element to the item's own element changed the serial")
            stripped = self.set_element(weapon, "impact")
            codec = self.dep("codec")
            readded = [b.part.value for b in codec.decode(self.set_element(stripped, "shock"))
                       if _is_element_part(b)]
            if any(_is_element_part(b) for b in codec.decode(stripped)) or readded != [INDEX_BY_ELEMENT["shock"]]:
                return HealthCheck(name, False, "impact strip / re-add failed")
            reseeded = self.set_seed(weapon, 1234)
            if self.get_seed(reseeded) != 1234 or self.set_seed(reseeded, KNOWN[0][7]) != weapon:
                return HealthCheck(name, False, "seed set/restore failed")
            if self.swap_parts(weapon, weapon, [0, 1]) != weapon:
                return HealthCheck(name, False, "self-swap changed the serial")
            try:
                self.swap_parts(weapon, shield, [0])
            except SerialError:
                pass
            else:
                return HealthCheck(name, False, "cross-category swap was not refused")
            if self.swap_parts(pearl, pearl, [0]) != pearl:
                return HealthCheck(name, False, "pearl self-swap changed the serial")
        except Exception as ex:
            return HealthCheck(name, False, "%s: %s" % (type(ex).__name__, ex))
        return HealthCheck(name, True, "element, seed and swap round-trip; cross-category swap refused")


MODULE = OpsModule
