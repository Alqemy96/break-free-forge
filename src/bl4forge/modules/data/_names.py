"""Display-name helpers (pure functions; the item-name table is passed in).

IMPORTANT: this is presentation only. `prettify_part` turns a raw part name into a label and, for a
composition part (`comp_05_legendary_x`), prefixes the tier word that is encoded in the NAME. That
prefix is the legacy display label, NOT the part's rarity: 14 of the 20 pearlescents are named
`comp_05_legendary_*` and read "Legendary" here. The authority for rarity, display name and pack is
`DataModule.part_meta()` (part_meta.json's explicit fields). Nothing in this module feeds a rarity
decision from these labels.
"""
from __future__ import annotations

import re
from typing import Mapping, Optional, Tuple

from ...core.vocab import RARITIES

_COMP_RE = re.compile(r"^comp_(\d+)_([a-z]+)(?:_(.+))?$")


def _comp_label(raw: str) -> Optional[Tuple[str, Optional[str]]]:
    """`comp_05_legendary_hellwalker` -> ("Legendary", "hellwalker") (display label only)."""
    m = _COMP_RE.match(raw or "")
    if not m:
        return None
    tier = int(m.group(1))
    label = RARITIES[tier - 1] if 1 <= tier <= len(RARITIES) else m.group(2).capitalize()
    return label, m.group(3)


def prettify_legendary(raw_suffix: Optional[str], item_names: Mapping[str, str]) -> Optional[str]:
    """`hellwalker` -> `Hellwalker`, preferring the game's own name table.

    None when the suffix carries no name (class mods use numbered compositions such as
    `comp_05_legendary_04`, where "04" is a slot index, not something to show a player).
    """
    key = (raw_suffix or "").strip().lower()
    if not key or key.isdigit():
        return None
    for candidate in ("np_" + key, key):
        if candidate in item_names:
            return item_names[candidate]
    return key.replace("_", " ").title()


def prettify_part(raw: Optional[str], item_names: Mapping[str, str]) -> str:
    """`part_scope_02_lens_02` -> `Scope 02 Lens 02`; `comp_05_legendary_x` -> `Legendary \u2014 X`."""
    raw = "" if raw is None else str(raw)
    comp = _comp_label(raw)
    if comp:
        label, name = comp
        pretty = prettify_legendary(name, item_names) if name else None
        return "%s — %s" % (label, pretty) if pretty else label
    s = raw
    if s.startswith("part_"):
        s = s[len("part_"):]
    s = s.replace("_", " ").strip()
    return " ".join(w.upper() if w.isupper() else w.capitalize() for w in s.split())
