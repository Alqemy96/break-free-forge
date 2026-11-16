"""Query -> row filter (private to the catalog module). Ports legacy `_matches` and its alias tables."""
from __future__ import annotations

from types import MappingProxyType
from typing import Optional, Tuple

from ...core import vocab
from ...core.types import SearchQuery
from ._db import Row

# What a user types -> the tokens the database actually stores. The database writes `assaultrifle`
# and `repairkit` (no underscore) in weaponType but `repair_kit` in type, so both spellings are
# listed. Copied from legacy `forge._matches`; matching is by SUBSTRING of weaponType + type.
TYPE_ALIASES = MappingProxyType({
    "ar": ("assaultrifle", "assault_rifle"),
    "assault_rifle": ("assaultrifle", "assault_rifle"),
    "assaultrifle": ("assaultrifle", "assault_rifle"),
    "rifle": ("assaultrifle", "assault_rifle"),
    "repkit": ("repairkit", "repair_kit"),
    "repair_kit": ("repairkit", "repair_kit"),
    "repairkit": ("repairkit", "repair_kit"),
    "classmod": ("classmod",),
    "class_mod": ("classmod",),
    "com": ("classmod",),
    "grenade": ("gadget",),
    "ordnance": ("gadget",),
    "launcher": ("heavy",),
    "rocket": ("heavy",),
    "sr": ("sniper",),
    "smg": ("smg",),
    "sg": ("shotgun",),
    "ps": ("pistol",),
})


def _clean(value: Optional[str]) -> str:
    return value.strip() if isinstance(value, str) else ""


class RowFilter:
    """A compiled query. Immutable; `matches(row)` is the conjunction of every filter that was given."""
    __slots__ = ("q", "kinds", "element", "manufacturer", "rarity", "character")

    def __init__(self, q: str, kinds: Tuple[str, ...], element: Optional[str], manufacturer: str,
                 rarity: str, character: str):
        self.q, self.kinds, self.element = q, kinds, element
        self.manufacturer, self.rarity, self.character = manufacturer, rarity, character

    def matches(self, row: Row) -> bool:
        if self.q and self.q not in row.name_l:
            return False
        if self.kinds and not any(k in row.kind for k in self.kinds):
            return False
        if self.element is not None and row.entry.element != self.element:
            return False
        if self.manufacturer and self.manufacturer not in row.manufacturer_l:
            return False
        if self.rarity and self.rarity not in row.rarity_l:
            return False
        if self.character and self.character not in row.source_l:
            return False
        return True


def compile_query(query: SearchQuery) -> Optional[RowFilter]:
    """Normalise a SearchQuery into a RowFilter, or None when no row can possibly match.

    None happens for an element name the vocabulary does not know ('plasma'): legacy returned
    nothing for it too (it compared the raw word to the database label). An unknown character is
    NOT an error: like legacy it is used as a raw keyword against the row's `source`.
    """
    element = None
    wanted_element = _clean(query.element)
    if wanted_element:
        try:
            element = vocab.normalize_element(wanted_element)
        except ValueError:
            return None
    kinds: Tuple[str, ...] = ()
    wanted_type = _clean(query.type)
    if wanted_type:
        t = wanted_type.lower().replace(" ", "_")
        kinds = TYPE_ALIASES.get(t, (t,))
    character = ""
    wanted_char = _clean(query.character)
    if wanted_char:
        try:
            character = vocab.normalize_character(wanted_char) or ""
        except ValueError:
            character = wanted_char.lower()
    return RowFilter(
        q=_clean(query.query).lower(),
        kinds=kinds,
        element=element,
        manufacturer=_clean(query.manufacturer).lower(),
        rarity=_clean(query.rarity).lower(),
        character=character,
    )
