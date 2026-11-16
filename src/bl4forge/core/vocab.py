"""Shared vocabulary: the single source of truth for names used by more than one module.

The legacy forge kept two element alias tables with different conventions ("shock" in the parts
database, "electric" in the serial database). Duplicated vocabulary is exactly the kind of drift
this module exists to prevent: normalise here, translate at the edge.
"""
from __future__ import annotations

from typing import Optional

# Canonical element names (lower-case). "impact" is plain kinetic damage: on a weapon it means
# NO element part is present. Gear (shields, class mods, repkits, enhancements) has no element.
ELEMENTS = ("cryo", "fire", "radiation", "shock", "corrosive", "impact")

ELEMENT_ALIASES = {
    "cryo": "cryo", "ice": "cryo",
    "fire": "fire", "incendiary": "fire", "burn": "fire",
    "radiation": "radiation", "rad": "radiation",
    "shock": "shock", "electric": "shock", "lightning": "shock",
    "corrosive": "corrosive", "corrosion": "corrosive", "corrode": "corrosive", "acid": "corrosive",
    "impact": "impact", "none": "impact", "non-elemental": "impact", "kinetic": "impact",
}

ELEMENT_LABELS = {
    "cryo": "Cryo", "fire": "Fire", "radiation": "Radiation",
    "shock": "Shock", "corrosive": "Corrosive", "impact": "Impact",
}

# Rarity ladder, lowest to highest. Rank decides which composition part "governs" an item.
RARITIES = ("Common", "Uncommon", "Rare", "Epic", "Legendary", "Pearl", "Vile")
RARITY_RANK = {name: i + 1 for i, name in enumerate(RARITIES)}

CHARACTERS = ("gravitar", "dark_siren", "exo_soldier", "paladin")
CHARACTER_ALIASES = {
    "gravitar": "gravitar",
    "dark_siren": "dark_siren", "dark siren": "dark_siren", "dark-siren": "dark_siren",
    "exo_soldier": "exo_soldier", "exo soldier": "exo_soldier", "exo-soldier": "exo_soldier",
    "paladin": "paladin",
}


def normalize_element(value: Optional[str]) -> Optional[str]:
    """'Electric' -> 'shock'. Returns None for empty input; raises ValueError if unknown."""
    if value is None or not str(value).strip():
        return None
    key = str(value).strip().lower()
    if key not in ELEMENT_ALIASES:
        raise ValueError("unknown element %r (known: %s)" % (value, ", ".join(ELEMENTS)))
    return ELEMENT_ALIASES[key]


def normalize_character(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    key = str(value).strip().lower()
    if key not in CHARACTER_ALIASES:
        raise ValueError("unknown character %r (known: %s)" % (value, ", ".join(CHARACTERS)))
    return CHARACTER_ALIASES[key]
