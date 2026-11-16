"""The part-resolution walk behind both rules: which (category, index) pairs does a serial hold?

Private to the `rules` module. It is a small re-implementation of what the legacy `describe` does,
written against the `codec` and `data` ports only (ops depends on rules, so rules cannot use ops).

How a PART block is read:
- `{N}`       bare part (subtype NONE): index N in the item's OWN category table.
- `{cat:idx}` integer part (subtype INT): index `idx` in category `cat`'s table.
- `{cat:[a b c]}` list part (subtype LIST): indexes a, b, c in category `cat`'s table. Legacy
  `describe` ignored the list values and looked `cat` up as an index in the item's own table (see
  CONTRACT.md, Deviations); each listed index is a real part and is judged on its own here.
"""
from __future__ import annotations

import re
from typing import Iterator, List, Mapping, NamedTuple, Optional, Sequence, Tuple

from ...core import vocab
from ...core.types import Block, PartRef, SUBTYPE_INT, SUBTYPE_LIST, TOK_PART

# Elements live in the shared "Weapon" category (id 1); these are the element part indexes there.
ELEMENT_CATEGORY = 1
ELEMENT_PART_INDEXES = frozenset((10, 11, 12, 13, 14))

# Composition parts encode rarity in their name: comp_0X_<kind>[_<name>]. The tier only seeds a
# FALLBACK rarity; the game's explicit part_meta rarity always wins (14 of 20 pearlescents are
# named comp_05_legendary_*).
_COMP = re.compile(r"^comp_(\d+)_([a-z]+)(?:_(.+))?$")


class Resolved(NamedTuple):
    ref: PartRef
    meta: Mapping[str, object]
    listed: bool                    # True when the part came out of a `{cat:[...]}` list


def coords(blocks: Sequence[Block], category_id: Optional[int]) -> Iterator[Tuple[int, Optional[int], int, bool]]:
    """(token_index, category_id, index, listed) for every part reference in the stream, in order."""
    for i, b in enumerate(blocks):
        p = b.part
        if b.token != TOK_PART or p is None:
            continue
        if p.subtype == SUBTYPE_INT:
            yield i, p.index, p.value, False
        elif p.subtype == SUBTYPE_LIST:
            for v in p.values:
                yield i, p.index, v, True
        else:
            yield i, category_id, p.index, False


def resolve(data, blocks: Sequence[Block], category_id: Optional[int]) -> List[Resolved]:
    """Every part reference with its manifest name, game meta and display label (legacy `describe`)."""
    names = data.category_names()
    out: List[Resolved] = []
    for i, cat, idx, listed in coords(blocks, category_id):
        raw = data.part_table(cat).get(idx)
        name = data.prettify_part(raw) if raw else None
        link = None
        if raw is None and not listed and idx in names:
            # A plain {N} with no entry in the item's table, where N is itself a category id, is a
            # cross-category pointer (the "firmware" parts), not an unknown part.
            name = "%s (category link)" % names[idx]
            link = idx
        meta = data.part_meta(cat, idx)
        if raw and raw.startswith("comp_") and meta.get("rarity"):
            name = "%s — %s" % (meta["rarity"], meta["name"]) if meta.get("name") else str(meta["rarity"])
        out.append(Resolved(PartRef(i, cat, idx, raw, name, link), meta, listed))
    return out


def comp_rarity(raw: Optional[str], meta: Mapping[str, object]) -> Optional[str]:
    """Rarity of a composition part (meta first, name tier as the fallback); None if not a comp part."""
    m = _COMP.match(raw or "")
    if not m:
        return None
    tier = int(m.group(1))
    fallback = vocab.RARITIES[tier - 1] if 1 <= tier <= len(vocab.RARITIES) else m.group(2).capitalize()
    return str(meta.get("rarity") or fallback)


def governing_rarity(rarities: Sequence[str]) -> Optional[str]:
    """The highest-tier rarity (first one wins a tie), or None for no composition parts."""
    best: Optional[str] = None
    best_rank = -1
    for r in rarities:
        rank = vocab.RARITY_RANK.get(r, 0)
        if rank > best_rank:
            best, best_rank = r, rank
    return best
