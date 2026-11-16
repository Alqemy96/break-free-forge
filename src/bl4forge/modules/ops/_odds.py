"""Drop-odds estimate and its one-line summary. Pure functions; the drop tables are passed in.

These are BASE RATES. The player's luck stat and area/event modifiers are resolved by the game at
runtime and are not present in any extracted data, so nothing here may be presented as exact.
"""
from __future__ import annotations

import copy
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional

# World-drop rarity weights (Appendix C, `rarity_balance`). They sum exactly to the published total,
# so there are no hidden tiers. Pearl and Vile have no world-drop weight: they are not estimated.
RARITY_WEIGHTS: Mapping[str, float] = MappingProxyType({
    "Common": 100.0,
    "Uncommon": 6.0,
    "Rare": 0.14,
    "Epic": 0.045,
    "Legendary": 0.0003,
})
RARITY_WEIGHT_TOTAL = 106.1853


def estimate(rarity: Optional[str], legendary_name: Optional[str], available: bool,
             probabilities: Mapping[str, object], drops_by_item: Mapping[str, List[dict]]) -> Dict[str, Any]:
    """World-drop and dedicated-drop odds for one described item.

    Explicitly an estimate. In the bundled drops.json, boss records carry an empty `drop_tier` and a
    zeroed `drop_chance` (the tier inference pass was not run), so dedicated sources are listed
    WITHOUT a rate unless the file actually supplies one. The published tier table is exposed as
    `dedicated_tier_rates` so a caller can say "if this is a Primary drop, it's 6%".
    """
    out: Dict[str, Any] = {
        "rarity": rarity,
        "tier_odds": None,
        "item_odds": None,
        "sources": [],
        "dedicated_tier_rates": copy.deepcopy(probabilities) if available else {},
    }

    weight = RARITY_WEIGHTS.get(rarity) if rarity else None
    p_tier = weight / RARITY_WEIGHT_TOTAL if weight else None
    if p_tier:
        out["tier_odds"] = {"probability": p_tier, "one_in": int(round(1.0 / p_tier))}

    if legendary_name and available:
        pool_share = None
        for d in drops_by_item.get(legendary_name.strip().lower(), []):
            chance = d.get("drop_chance") or 0.0
            entry = {
                "source": d.get("source_display") or d.get("source"),
                "source_type": d.get("source_type"),
                "tier": d.get("drop_tier") or None,
                "chance": chance if chance > 0 else None,
                "pool": d.get("pool"),
            }
            if d.get("source_type") == "WorldDrop":
                # For world drops, `drop_chance` is this item's share of its rarity pool, not an
                # absolute rate.
                entry["pool_share"] = chance if chance > 0 else None
                entry["chance"] = None
                if chance > 0:
                    pool_share = chance
            out["sources"].append(entry)

        # Absolute per-item world-drop odds = P(rarity tier) x share of pool.
        if p_tier and pool_share:
            p_item = p_tier * pool_share
            out["item_odds"] = {"probability": p_item, "one_in": int(round(1.0 / p_item))}

        out["sources"].sort(key=lambda s: (s["source_type"] != "Boss", -(s.get("chance") or 0)))
    return out


def summarize(est: Mapping[str, object]) -> str:
    """One-line human summary of drop odds. Says nothing it cannot support."""
    bits: List[str] = []
    item_odds = est.get("item_odds")
    tier_odds = est.get("tier_odds")
    if item_odds:
        bits.append("world drop ~1 in %s" % f"{item_odds['one_in']:,}")           # type: ignore[index]
    elif tier_odds:
        bits.append("any %s world drop ~1 in %s"
                    % ((est.get("rarity") or "?").lower(), f"{tier_odds['one_in']:,}"))  # type: ignore[index,union-attr]

    sources = est.get("sources") or []
    bosses = [s for s in sources if s["source_type"] == "Boss"]      # type: ignore[union-attr]
    for s in bosses[:3]:
        if s.get("chance"):
            bits.append("%s %.1f%%" % (s["source"], s["chance"] * 100))
        elif s.get("tier"):
            bits.append("%s (%s)" % (s["source"], s["tier"].lower()))
        else:
            bits.append("dedicated: %s" % s["source"])
    if len(bosses) > 3:
        bits.append("+%d more sources" % (len(bosses) - 3))
    return " · ".join(bits)
