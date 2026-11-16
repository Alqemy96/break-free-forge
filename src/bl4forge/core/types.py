"""Plain data shared across module boundaries.

Rules: types here are dumb (no behaviour beyond tiny helpers), immutable where practical, and
JSON-friendly via `to_dict`. A module may define private helper types of its own, but anything
that crosses a port lives here so neighbours never import each other's internals.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

# ---- serial bitstream (produced/consumed by the codec module) -------------------------------

TOK_SEP1 = 0     # hard separator / terminator  "|"
TOK_SEP2 = 1     # soft separator               ","
TOK_VARINT = 2   # nibble varint
TOK_VARBIT = 3   # length-prefixed varint
TOK_PART = 4     # complex part  {i} {i:v} {i:[..]}
TOK_STRING = 5   # length-prefixed 7-bit string

SUBTYPE_NONE = 0
SUBTYPE_INT = 1
SUBTYPE_LIST = 2


@dataclass(frozen=True)
class Part:
    index: int
    subtype: int = SUBTYPE_NONE
    value: int = 0
    values: Tuple[int, ...] = ()


@dataclass(frozen=True)
class Block:
    token: int
    value: int = 0
    value_str: str = ""
    part: Optional[Part] = None


Blocks = Tuple[Block, ...]   # a decoded serial: immutable; transforms return new tuples


# ---- identification (produced by ops, consumed by catalog/builder/render/cli) ---------------

@dataclass(frozen=True)
class PartRef:
    """One resolved part of a decoded serial. Positions are `token_index` into Blocks."""
    token_index: int
    category_id: Optional[int]
    index: int
    raw: Optional[str]            # manifest name, e.g. "comp_05_legendary_temper"; None if unknown
    name: Optional[str]           # display name
    category_link: Optional[int] = None   # set when a bare {N} points at another category

    def label(self) -> str:
        if self.name:
            return self.name
        where = "%s:%d" % (self.category_id, self.index) if self.category_id else str(self.index)
        return "Unknown part %s" % where


@dataclass(frozen=True)
class ItemInfo:
    """Everything the bitstream + manifest can say about one serial. The bitstream is authoritative."""
    serial: str
    category_id: Optional[int] = None
    category: Optional[str] = None
    level: Optional[int] = None
    rarity: Optional[str] = None            # one of vocab.RARITIES, from part_meta (never from name)
    element: Optional[str] = None           # vocab.ELEMENTS member; None for gear
    legendary_name: Optional[str] = None
    display_name: Optional[str] = None
    parts: Tuple[PartRef, ...] = ()
    other_components: Tuple[Tuple[str, Optional[str]], ...] = ()   # (rarity, name) of lower-tier comps
    tokens: str = ""
    content_pack: str = "coregame"
    content_pack_label: str = "Base game"
    owned: bool = True
    manifest_ok: bool = True
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


# ---- save files (produced by the save module, consumed by cli/web) -------------------------

@dataclass(frozen=True)
class SaveItem:
    """One serial line in a save's YAML. `ref` is the stable address ("backpack/slot_3",
    "equipped/slot_0", "lostloot/2"); `line` is the 1-based line number of the serial: line."""
    ref: str
    area: str                 # backpack | equipped | lostloot
    slot: str                 # slot_N for backpack/equipped; the list index for lostloot
    serial: str
    line: int

    def to_dict(self) -> dict:
        return asdict(self)


# ---- catalog --------------------------------------------------------------------------------

@dataclass(frozen=True)
class CatalogEntry:
    """One row of the community serial database, cleaned. Labels here are HINTS, not truth."""
    serial: str
    name: str = "?"
    type: str = ""                # weapon | shield | classmod | repair_kit | gadget | enhancement
    weapon_type: str = ""         # pistol | shotgun | smg | assaultrifle | sniper | heavy | ...
    manufacturer: str = ""
    label: str = ""               # e.g. "Jakobs Pistol"
    rarity: str = ""
    element: Optional[str] = None  # vocab element or None (db said N/A); db label, may be wrong
    source: str = ""


@dataclass(frozen=True)
class SearchQuery:
    query: Optional[str] = None
    type: Optional[str] = None            # accepts aliases: ar, sg, ps, repkit, grenade, ...
    element: Optional[str] = None
    manufacturer: Optional[str] = None
    rarity: Optional[str] = None
    character: Optional[str] = None
    limit: int = 25
    verify_element: bool = True           # re-check element against the decoded serial
    include_unowned: bool = False


@dataclass(frozen=True)
class SearchResult:
    entries: Tuple[CatalogEntry, ...] = ()
    hidden_by_pack: Dict[str, int] = field(default_factory=dict)   # filtered, reported not silent
    dropped_element_mismatch: int = 0


# ---- loadouts -------------------------------------------------------------------------------

@dataclass(frozen=True)
class LoadoutRequest:
    """One spec entry. Either `serial` (explicit) or search fields (auto-pick)."""
    group: Optional[str] = None
    serial: Optional[str] = None
    query: Optional[str] = None
    type: Optional[str] = None
    element: Optional[str] = None
    manufacturer: Optional[str] = None
    rarity: Optional[str] = None
    character: Optional[str] = None
    count: int = 1
    note: str = ""
    display_name: Optional[str] = None
    label: str = ""               # explicit entries: manufacturer/type label to show
    name: str = ""                # explicit entries: item name hint

    @classmethod
    def from_dict(cls, d: dict) -> "LoadoutRequest":
        """Parse one JSON spec entry (legacy keys accepted: `label_name` = `display_name`)."""
        known = {f for f in cls.__dataclass_fields__}
        data = {k: v for k, v in d.items() if k in known}
        if "display_name" not in data and d.get("label_name"):
            data["display_name"] = d["label_name"]
        if "count" in data:
            data["count"] = int(data["count"])
        return cls(**data)


@dataclass(frozen=True)
class LoadoutItem:
    name: str
    serial: str
    level: Optional[int]
    group: Optional[str] = None
    display_name: Optional[str] = None
    manufacturer: str = ""
    label: str = ""
    type: str = ""
    weapon_type: str = ""
    rarity: str = ""                 # best truth: decoded rarity, else catalog hint
    element: Optional[str] = None    # best truth: decoded element, else catalog hint
    category: Optional[str] = None
    legendary_name: Optional[str] = None
    parts: Tuple[str, ...] = ()
    odds: str = ""
    source: str = ""
    note: str = ""
    warnings: Tuple[str, ...] = ()

    @property
    def shown_name(self) -> str:
        return self.display_name or self.legendary_name or self.name


@dataclass(frozen=True)
class Loadout:
    title: str
    level: Optional[int]
    items: Tuple[LoadoutItem, ...] = ()
    groups: Tuple[str, ...] = ()
    unmatched: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()


# ---- health ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class HealthCheck:
    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class HealthReport:
    ok: bool
    checks: Tuple[HealthCheck, ...] = ()
    summary: str = ""

    @staticmethod
    def from_checks(checks: List[HealthCheck], summary: str = "") -> "HealthReport":
        return HealthReport(ok=all(c.ok for c in checks), checks=tuple(checks), summary=summary)
