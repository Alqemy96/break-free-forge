"""Known-answer serials for OpsModule.health(). Hard-coded; health() never opens a file for these.

Each row: (label, serial, category_id, level, rarity, element, legendary_name, seed, other_components).
Expected values were taken from the legacy `partsdb.describe` (the parity oracle) when this module
was written. The `pearl` rows are NOT community-database serials: they are database serial
`@Ugy>*^2}TYg%%uv-...` (an Order Sniper, "Symmetry") with its composition part's index swapped to 84
(`comp_05_legendary_temper`, tagged Pearl in part_meta.json) - the real example of a pearlescent whose
raw part name says "legendary". The database itself holds no pearlescent.
"""
from __future__ import annotations

KNOWN = (
    ("weapon (Maliwan SMG, shock)",
     "@Ugw$Yw2}TYg47UXOhbq*fh7R>Zy+o}<?L&2H4yqRF9BNnq",
     21, 50, "Legendary", "shock", "Plasma Coil", 1132, ()),
    ("shield (Ripper, no element)",
     "@Uge8^+m/)}}!tC#$M>VQ_G&h6?ieDH2",
     300, 50, "Legendary", None, "Sparky Shield", 3835, ()),
    ("pearlescent (Order Sniper, comp_05_legendary_temper)",
     "@Ugy>*^2}TYg%%uuSiz?Ki5)~7bsZQ-dtwPm8%/g9H?Lz<",
     26, 50, "Pearl", "impact", "Solar Temper", 2631, ()),
    ("pearlescent + legendary component (highest tier governs)",
     "@Ugy>*^2}TYg%%uuSiz?Ki5)~7bsZQ-dtwPm8%/g9H?L!R$",
     26, 50, "Pearl", "impact", "Solar Temper", 2631, (("Legendary", "Fisheye"),)),
)
