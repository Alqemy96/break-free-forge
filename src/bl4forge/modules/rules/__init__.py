"""rules: Decide what the player may hold (content-pack ownership) and whether a serial is structurally sound.

Two jobs, both answered per PART from the decoded serial (never from an item name or a database label):
- ownership: every part is tagged with the content pack it ships in (`part_meta`, default
  "coregame"); an item is owned only if every one of its parts' packs is owned;
- structure: parts resolve, one composition (rarity) part, at most one element, a sane level.

The owned-pack set is per-instance state seeded from `config.owned_packs`. Nothing here is global.
See CONTRACT.md in this directory.


DISCLOSURE (what this code does)
  Reads: nothing from disk. Writes: nothing. Network: none. Risk: none (pure computation on values passed in).
"""
from __future__ import annotations

from types import MappingProxyType
from typing import FrozenSet, Iterable, List, Optional, Tuple

from ...core.errors import ConfigError, SerialError
from ...core.module import Module, ModuleContext
from ...core.ports import RulesPort
from ...core.types import Blocks, HealthCheck, HealthReport
from . import _known as K
from ._walk import ELEMENT_CATEGORY, ELEMENT_PART_INDEXES, comp_rarity, coords, governing_rarity, resolve

BASE_PACK = "coregame"

# Pack key -> display label. A pack the game adds that is not listed here is labelled by its key.
CONTENT_PACKS = MappingProxyType({
    "coregame": "Base game",
    "bounty_pack_1": "Bounty Pack 1 - How Rush Saved Mercenary Day",
    "bounty_pack_2": "Bounty Pack 2 - Legend of the Stone Demon",
    "bounty_pack_3": "Bounty Pack 3 - A Zane to Kill For",
    "bounty_pack_4": "Bounty Pack 4 - Murders & Acquisitions",
    "story_pack_1": "Story Pack 1 - Mad Ellie and the Vault of the Damned",
})

NO_MANIFEST = "manifest data unavailable — cannot validate"      # legacy wording, kept verbatim
_LEVEL_RANGE = (1, 255)


class RulesModule(Module):
    name = "rules"
    purpose = "Decide what the player may hold (content-pack ownership) and whether a serial is structurally sound."
    requires = ('codec', 'data')
    port = RulesPort

    CONTENT_PACKS = CONTENT_PACKS

    def __init__(self, ctx: ModuleContext):
        super().__init__(ctx)
        self._codec = self.dep("codec")
        self._data = self.dep("data")
        self._owned: FrozenSet[str] = frozenset(self.config.owned_packs)

    # ---- ownership ----------------------------------------------------------------------------
    def owned_packs(self) -> FrozenSet[str]:
        """The content packs the player owns (this instance's set, seeded from the config)."""
        return self._owned

    def set_owned_packs(self, packs: Iterable[str]) -> None:
        """Replace THIS instance's owned-pack set (extra to the port; no other instance is touched)."""
        if isinstance(packs, str):
            raise ConfigError("owned packs must be a collection of pack keys, not one string")
        packs = tuple(packs)
        if not all(isinstance(p, str) for p in packs):
            raise ConfigError("owned packs must be pack keys (strings)")
        self._owned = frozenset(packs)

    def pack_label(self, pack: str) -> str:
        """Display label for a pack key; an unlisted key is returned as is."""
        label = CONTENT_PACKS.get(pack) if isinstance(pack, str) else None
        return label if label is not None else str(pack)

    def pack_of(self, category_id: Optional[int], index: int) -> str:
        """Content pack of one part reference. part_meta is the only source; a missing tag is base game."""
        meta = self._data.part_meta(category_id, index)
        pack = meta.get("pack") if meta else None
        return pack if isinstance(pack, str) and pack else BASE_PACK

    def is_owned(self, category_id: Optional[int], index: int) -> bool:
        pack = self.pack_of(category_id, index)
        return pack == BASE_PACK or pack in self._owned

    def serial_ownership(self, serial: str) -> Tuple[bool, Optional[str]]:
        """(owned, first_missing_pack_or_None), judged part by part.

        An item is owned only if EVERY part's pack is owned, whatever the item is called. When it is
        not, the pack named is the alphabetically first one among the missing packs. Raises
        SerialError if the serial cannot be decoded.
        """
        blocks = self._blocks(serial)
        owned = self._owned                       # one snapshot for the whole walk
        missing = set()
        for _i, cat, idx, _listed in coords(blocks, self._codec.get_category_id(blocks)):
            pack = self.pack_of(cat, idx)
            if pack != BASE_PACK and pack not in owned:
                missing.add(pack)
        return (False, min(missing)) if missing else (True, None)

    # ---- structure ----------------------------------------------------------------------------
    def validate(self, serial: str) -> List[str]:
        """Structural problems with a serial, as human-readable strings; [] means none were found.

        STRUCTURAL CHECKS ONLY: every part resolves in the manifest, one composition (rarity) part
        (a pearlescent may carry two), at most one element part, a level in 1-255. Passing says
        nothing about in-game validity; the finer part-compatibility rules (barrel/accessory
        pairing, slot caps) need data the manifest does not carry and are not checked. Raises
        SerialError if the serial cannot be decoded.
        """
        blocks = self._blocks(serial)
        data = self._data
        if not data.available():
            return [NO_MANIFEST]
        category_id = self._codec.get_category_id(blocks)
        names = data.category_names()
        parts = resolve(data, blocks, category_id)
        problems: List[str] = []

        for r in parts:
            ref = r.ref
            if not ref.raw and ref.category_link is None:
                problems.append("part index %s does not exist in the %s table"
                                % (ref.index, names.get(ref.category_id) or ref.category_id))

        comps = [(r.ref, comp_rarity(r.ref.raw, r.meta)) for r in parts if r.ref.raw]
        comps = [(ref, rarity) for ref, rarity in comps if rarity is not None]
        if not comps:
            # Not automatically wrong: 62 of the 9,875 community codes carry none (Daedalus ARs,
            # Ripper gadgets), so report an unknown rarity rather than a broken item.
            problems.append("no composition part — rarity cannot be determined "
                            "(a few unique/mission items legitimately have none)")
        elif len(comps) > 1 and governing_rarity([rarity for _ref, rarity in comps]) != "Pearl":
            # A pearlescent legitimately carries two (its named pearl component plus a plain
            # legendary one); only an item with no Pearl-tier component is flagged.
            problems.append("%d composition parts (%s) — a non-pearlescent item may only have one rarity"
                            % (len(comps), ", ".join(ref.label() for ref, _r in comps)))

        elements = [r.ref for r in parts
                    if r.ref.category_id == ELEMENT_CATEGORY and r.ref.index in ELEMENT_PART_INDEXES]
        if len(elements) > 1:
            problems.append("%d element parts (%s) — only one is valid"
                            % (len(elements), ", ".join(ref.label() for ref in elements)))

        level = self._codec.get_level(blocks)
        if level is None:
            problems.append("no level field could be located")
        elif not (_LEVEL_RANGE[0] <= level <= _LEVEL_RANGE[1]):
            problems.append("level %s is outside the usable range %d-%d" % ((level,) + _LEVEL_RANGE))
        return problems

    # ---- plumbing -----------------------------------------------------------------------------
    def _blocks(self, serial: str) -> Blocks:
        try:
            return self._codec.decode(serial)
        except SerialError:
            raise
        except Exception as ex:      # a codec double may leak other errors; the port promises SerialError
            raise SerialError("cannot decode serial: %s: %s" % (type(ex).__name__, ex)) from ex

    # ---- self-check ---------------------------------------------------------------------------
    def health(self) -> HealthReport:
        checks: List[HealthCheck] = []
        try:
            for check in (self._check_data, self._check_label, self._check_base_game,
                          self._check_story_pack, self._check_bounty_pack, self._check_list_parts,
                          self._check_structure, self._check_errors):
                try:
                    checks.append(check())
                except Exception as ex:
                    checks.append(HealthCheck(getattr(check, "__name__", "check").replace("_check_", ""),
                                              False, "%s: %s" % (type(ex).__name__, ex)))
        except Exception as ex:  # health() must never raise
            checks.append(HealthCheck("health-run", False, "%s: %s" % (type(ex).__name__, ex)))
        bad = [c.name for c in checks if not c.ok]
        owned = ", ".join(sorted(self._owned)) or "none"
        summary = ("%d known-answer checks passed; owns %s" % (len(checks), owned)) if not bad \
            else "failed: " + ", ".join(bad)
        return HealthReport.from_checks(checks, summary)

    def _check_data(self) -> HealthCheck:
        if not self._data.available():
            return HealthCheck("manifest", False, "manifest data unavailable: every part reads as base game")
        return HealthCheck("manifest", True, "manifest present")

    def _check_label(self) -> HealthCheck:
        got = self.pack_label(BASE_PACK)
        return HealthCheck("pack-label", got == "Base game", "pack_label('coregame') = %r" % got)

    def _check_base_game(self) -> HealthCheck:
        got = self.serial_ownership(K.BASE_SERIAL)
        return HealthCheck("base-game-owned", got == (True, None), "base-game serial -> %r" % (got,))

    def _check_story_pack(self) -> HealthCheck:
        # Config-independent facts first, then the verdict the CURRENT owned set must give.
        cat, idx = K.STORY_PACK_REF
        pack = self.pack_of(cat, idx)
        if pack != K.STORY_PACK:
            return HealthCheck("story-pack-1", False, "pack_of(%d, %d) = %r, expected %r"
                               % (cat, idx, pack, K.STORY_PACK))
        want = (True, None) if K.STORY_PACK in self._owned else (False, K.STORY_PACK)
        got = self.serial_ownership(K.STORY_PACK_SERIAL)
        return HealthCheck("story-pack-1", got == want and self.is_owned(cat, idx) == want[0],
                           "Story Pack 1 serial -> %r (expected %r)" % (got, want))

    def _check_bounty_pack(self) -> HealthCheck:
        # A real item: base-game name and composition, one Bounty Pack 3 barrel.
        cat, idx = K.BOUNTY_REF
        pack = self.pack_of(cat, idx)
        if pack != K.BOUNTY_PACK:
            return HealthCheck("ownership-per-part", False, "pack_of(%d, %d) = %r, expected %r"
                               % (cat, idx, pack, K.BOUNTY_PACK))
        want = (True, None) if K.BOUNTY_PACK in self._owned else (False, K.BOUNTY_PACK)
        got = self.serial_ownership(K.BOUNTY_SERIAL)
        return HealthCheck("ownership-per-part", got == want, "DLC barrel on a base-game gun -> %r (expected %r)"
                           % (got, want))

    def _check_list_parts(self) -> HealthCheck:
        blocks = self._blocks(K.KIT_SERIAL)
        refs = list(coords(blocks, self._codec.get_category_id(blocks)))
        listed = [r for r in refs if r[3]]
        ok = (bool(listed) and all(r[2] in self._data.part_table(r[1]) for r in listed)
              and self.serial_ownership(K.KIT_SERIAL) == (True, None))
        return HealthCheck("list-parts", ok, "%d listed part refs resolve" % len(listed))

    def _check_structure(self) -> HealthCheck:
        base = self.validate(K.BASE_SERIAL)
        two = self.validate(K.TWO_COMPS_SERIAL)
        pearl = self.validate(K.PEARL_TWO_COMPS_SERIAL)
        ok = (base == [] and len(two) == 1 and "composition parts" in two[0] and pearl == [])
        return HealthCheck("structure", ok, "clean=%r, two non-pearl comps=%d problem(s), pearl with two=%r"
                           % (base, len(two), pearl))

    def _check_errors(self) -> HealthCheck:
        for bad in ("", "@U", "not a serial"):
            for fn in (self.serial_ownership, self.validate):
                try:
                    fn(bad)
                except SerialError:
                    continue
                except Exception as ex:
                    return HealthCheck("errors-are-serialerror", False, "%r raised %s" % (bad, type(ex).__name__))
                return HealthCheck("errors-are-serialerror", False, "%r was accepted by %s" % (bad, fn.__name__))
        return HealthCheck("errors-are-serialerror", True, "garbage raises SerialError")


MODULE = RulesModule
