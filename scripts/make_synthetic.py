#!/usr/bin/env python3
"""Regenerate data/synthetic/ : the fictional demo and test dataset. SYNTHETIC - not game data.

DISCLOSURE (what this script does)
  Reads: nothing (every name, id and number below is invented in this file). Writes: only into
  the folder named by --out (default: <repo>/data/synthetic). Network: none. Risk: it overwrites the
  files it owns in that folder.

Every manufacturer, item, part, category id and serial here is made up. The serials are produced by
this repo's own codec (bl4forge.modules.codec), so they decode with it, but they are not real game
items and they will not exist in a real game. The output is deterministic: running this twice gives
identical files (tests check that the committed files match).

    python scripts/make_synthetic.py            # rewrite data/synthetic/
    python scripts/make_synthetic.py --check    # exit 1 if the committed files differ
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bl4forge.modules.codec import CodecModule  # noqa: E402
from bl4forge.core.config import Config  # noqa: E402
from bl4forge.core.module import ModuleContext  # noqa: E402

MARK = "SYNTHETIC — not game data"
VERSION_LINE = "SYNTHETIC — not game data (Breakfree demo set v1)"
LEVEL = 50

# (category id, file slug, category name, database weaponType, manufacturer, manufacturer label,
#  (legendary A, legendary B, pearlescent))
WEAPONS = [
    (9101, "breakfree_pistol", "Breakfree Pistol", "pistol", "BFA", "Breakfree Arms",
     ("Liberator", "Fine Print", "Skeleton Key")),
    (9102, "breakfree_shotgun", "Breakfree Shotgun", "shotgun", "BFA", "Breakfree Arms",
     ("Open Vault", "Right To Repair", "Warranty Void")),
    (9103, "breakfree_smg", "Breakfree SMG", "smg", "BFA", "Breakfree Arms",
     ("Free Radical", "Source Code", "Root Access")),
    (9104, "breakfree_assault_rifle", "Breakfree Assault Rifle", "assaultrifle", "BFA", "Breakfree Arms",
     ("Jailbreaker", "Open Source", "Public Domain")),
    (9105, "breakfree_sniper", "Breakfree Sniper", "sniper", "BFA", "Breakfree Arms",
     ("Uncapped", "Clear Sightline", "Fair Use")),
    (9106, "breakfree_heavy_weapon", "Breakfree Heavy Weapon", "heavy", "BFA", "Breakfree Arms",
     ("Unlicensed", "Hostile Takeover", "Buyback")),
    (9111, "openvault_pistol", "Openvault Pistol", "pistol", "OVC", "Open Vault Co",
     ("Gold Standard", "Sunset Clause", "Escape Hatch")),
    (9112, "openvault_shotgun", "Openvault Shotgun", "shotgun", "OVC", "Open Vault Co",
     ("Loophole", "Wide Berth", "Master Key")),
    (9113, "openvault_smg", "Openvault SMG", "smg", "OVC", "Open Vault Co",
     ("Backdoor", "Patch Notes", "Zero Day")),
]

# Gear: (category id, slug, category name, database type, weaponType label, manufacturer label,
#        source file, label, (legendary A, legendary B, pearlescent))
GEAR = [
    (9201, "breakfree_shield", "Breakfree Shield", "shield", "shield", "Breakfree Arms",
     "GunCodes_shield.txt", "Breakfree Shield", ("Safe Harbor", "Cold Storage", "Golden Parachute")),
    (9202, "breakfree_repair_kit", "Breakfree Repair Kit", "repair_kit", "repairkit", "Breakfree Arms",
     "GunCodes_repairkit.txt", "Breakfree Repair Kit", ("Second Wind", "Field Patch", "Full Refund")),
    (9203, "breakfree_grenade_gadget", "Breakfree Grenade Gadget", "gadget", "gadget", "Breakfree Arms",
     "GunCodes_gadget.txt", "Breakfree Grenade", ("Bad Debt", "Eviction Notice", "Hard Reset")),
    (9204, "breakfree_enhancement", "Breakfree Enhancement", "enhancement", "enhancement", "Breakfree Arms",
     "GunCodes_enhancement.txt", "Breakfree Enhancement", ("Tune Up", "Overclock", "Factory Reset")),
]

# Class mods: (category id, slug, category name, vocab character, db weaponType, label, legendary names)
CLASSMODS = [
    (9211, "breakfree_classmod_alpha", "Breakfree Class Mod Alpha", "gravitar", "classmod_gravitar",
     "Alpha Class Mod", ("Quiet Quitter", "Paper Trail", "Soft Landing")),
    (9212, "breakfree_classmod_beta", "Breakfree Class Mod Beta", "dark_siren", "classmod_dark_siren",
     "Beta Class Mod", ("Night Shift", "Fine Tooth", "Blank Check")),
    (9213, "breakfree_classmod_gamma", "Breakfree Class Mod Gamma", "exo_soldier", "classmod_exo_soldier",
     "Gamma Class Mod", ("Crash Test", "Dead Reckoning", "Clean Slate")),
    (9214, "breakfree_classmod_delta", "Breakfree Class Mod Delta", "paladin", "classmod_paladin",
     "Delta Class Mod", ("Iron Clause", "Hold Fast", "Last Stand Ltd")),
]

FIRMWARE_CAT, PERK_CAT = 9250, 9230
PACK3, STORY = "bounty_pack_3", "story_pack_1"
ELEMENT_IDX = {"corrosive": 10, "cryo": 11, "fire": 12, "radiation": 13, "shock": 14}


def slug(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())


def comp_name(legendary: str) -> str:
    return "comp_05_legendary_" + slug(legendary)


# ---- part tables ------------------------------------------------------------------------------

def weapon_table(legs) -> List[Tuple[int, str]]:
    rows = [(1, "comp_01_common"), (2, "comp_02_uncommon"), (3, "comp_03_rare"), (4, "comp_04_epic"),
            (5, comp_name(legs[0])), (6, comp_name(legs[1])), (7, comp_name(legs[2]))]
    n = 8
    for kind, count in (("body", 3), ("barrel", 4), ("mag", 2), ("grip", 2), ("scope", 2)):
        for k in range(count):
            rows.append((n, "part_%s_%02d" % (kind, k + 1)))
            n += 1
    rows.append((21, "part_barrel_pack3"))
    rows.append((22, "part_barrel_story"))
    return rows


def gear_table(legs, kind: str) -> List[Tuple[int, str]]:
    rows = [(1, "comp_01_common"), (2, "comp_02_uncommon"), (3, "comp_03_rare"), (4, "comp_04_epic"),
            (5, comp_name(legs[0])), (6, comp_name(legs[1])), (7, comp_name(legs[2]))]
    for k in range(3):
        rows.append((8 + k, "part_%s_%02d" % (kind, k + 1)))
    for k in range(2):
        rows.append((11 + k, "part_%s_aux_%02d" % (kind, k + 1)))
    return rows


def build_tables():
    """-> (category_names, {file: rows}, part_meta, item_names)"""
    cats: Dict[int, str] = {1: "Weapon", FIRMWARE_CAT: "Breakfree Firmware", PERK_CAT: "Breakfree Perks"}
    files: Dict[str, List[Tuple[int, str]]] = {}
    meta: Dict[str, dict] = {}
    names: Dict[str, str] = {}

    files["weapon-1"] = [(1, "base_comp_02_uncommon"), (2, "base_comp_03_rare"), (3, "base_comp_04_epic"),
                         (4, "base_comp_05_legendary"), (10, "part_corrosive"), (11, "part_cryo"),
                         (12, "part_fire"), (13, "part_radiation"), (14, "part_shock")]
    files["breakfree_firmware-%d" % FIRMWARE_CAT] = [(k, "part_firmware_%02d" % k) for k in range(1, 9)]
    files["breakfree_perks-%d" % PERK_CAT] = [(k, "part_perk_%02d" % k) for k in range(1, 13)]

    def register(cat: int, legs, table):
        for (i, nm), pearl_slot in zip(table[4:7], (False, False, True)):
            lname = legs[i - 5]
            names["np_" + slug(lname)] = lname
            entry = {"name": lname, "rarity": "Pearl" if pearl_slot else "Legendary",
                     "tags": ["pearlescent" if pearl_slot else "legendary", "unique"]}
            meta["%d:%d" % (cat, i)] = entry

    for cat, fslug, cname, _wt, _mc, _ml, legs in WEAPONS:
        cats[cat] = cname
        table = weapon_table(legs)
        files["%s-%d" % (fslug, cat)] = table
        register(cat, legs, table)
        meta["%d:21" % cat] = {"pack": PACK3, "name": "Pack 3 Barrel"}
        meta["%d:22" % cat] = {"pack": STORY, "name": "Story Barrel"}
    for cat, fslug, cname, dbtype, _wt, _ml, _src, _lab, legs in GEAR:
        cats[cat] = cname
        table = gear_table(legs, dbtype.split("_")[0])
        files["%s-%d" % (fslug, cat)] = table
        register(cat, legs, table)
    for cat, fslug, cname, _char, _wt, _lab, legs in CLASSMODS:
        cats[cat] = cname
        table = gear_table(legs, "mod")
        files["%s-%d" % (fslug, cat)] = table
        register(cat, legs, table)
    # some legendaries carry only a display name (no rarity), like a plain tagged part
    meta["%d:8" % FIRMWARE_CAT] = {"name": "Firmware Eight", "pack": PACK3}
    return cats, files, meta, names


# ---- serials -----------------------------------------------------------------------------------

class Maker:
    def __init__(self):
        self.codec = CodecModule(ModuleContext("codec", Config.default(root=ROOT), {}))
        self.rng = random.Random(20260101)

    def serial(self, category: int, parts: str, level: int = LEVEL) -> str:
        seed = self.rng.randrange(100, 4000)
        text = "%d, 0, 1, %d| 2, %d|| %s|" % (category, level, seed, parts)
        s = self.codec.encode(self.codec.from_string(text))
        assert self.codec.parts_string(self.codec.decode(s)) == text, text
        return s


def weapon_parts(rng, comp: int, element: str = None, barrel: int = None, elem_at: int = None) -> str:
    """elem_at: put the element part at this position instead of last. Two guns of one category with the
    element at positions 4 and 3 give a swap of position 3 alone that leaves two element parts, while
    swapping positions 3 and 4 together leaves one."""
    parts = ["{%d}" % comp, "{%d}" % rng.choice((8, 9, 10)),
             "{%d}" % (barrel if barrel else rng.choice((11, 12, 13, 14))),
             "{%d}" % rng.choice((15, 16)), "{%d}" % rng.choice((17, 18)), "{%d}" % rng.choice((19, 20))]
    if element:
        parts.insert(len(parts) if elem_at is None else elem_at, "{1:%d}" % ELEMENT_IDX[element])
    return " ".join(parts)


def gear_parts(rng, comp: int, extra: str = "", body_first: bool = False) -> str:
    """body_first: a body part before the composition part (so copying position 0 of this item onto a
    weapon leaves that weapon without a composition part)."""
    p = ["{%d}" % comp, "{%d}" % rng.choice((8, 9, 10)), "{%d}" % rng.choice((11, 12))]
    if body_first:
        p[0], p[1] = p[1], p[0]
    return " ".join(p) + (" " + extra if extra else "")


def build_rows(mk: Maker):
    """Database rows plus the named serials the tests rely on."""
    rows: List[dict] = []
    named: Dict[str, str] = {}
    rng = mk.rng

    def row(name, serial, typ, wtype, mfr, label, rarity, bullet, source):
        rows.append({
            "itemName": name, "partString": '"%s",' % serial, "type": typ, "weaponType": wtype,
            "manufacturer": mfr, "manufacturerWeaponType": label, "rarity": rarity,
            "bulletType": bullet, "timestamp": "2000-01-01 00:00:00", "source": source,
            "note": MARK})

    cycle = ["fire", "cryo", "shock", "corrosive", "radiation"]
    for k, (cat, fslug, cname, wtype, _code, mfr, legs) in enumerate(WEAPONS):
        label = cname
        src = "GunCodes_%s.txt" % wtype
        # legendary A, legendary B and the pearlescent get different elements (the pearlescent: none = impact)
        for comp, leg, rarity, el in ((5, legs[0], "Legendary", cycle[k % 5]),
                                      (6, legs[1], "Legendary", cycle[(k + 2) % 5]),
                                      (7, legs[2], "Pearl", None)):
            s = mk.serial(cat, weapon_parts(rng, comp, el, elem_at={(9102, 5): 4, (9102, 6): 3}.get((cat, comp))))
            row(leg, s, "weapon", wtype, mfr, label, rarity,
                {"shock": "electric", None: "impact"}.get(el, el), src)
            named["%d:%d" % (cat, comp)] = s
        s = mk.serial(cat, weapon_parts(rng, 4, "radiation"))
        row("Standard Issue " + cname.split()[-1], s, "weapon", wtype, mfr, label, "Epic", "radiation", src)
        named["epic:%d" % cat] = s

    # a database label that the serial contradicts (dropped by element verification)
    liar = mk.serial(9101, weapon_parts(rng, 5, "fire"))
    row("Liberator", liar, "weapon", "pistol", "Breakfree Arms", "Breakfree Pistol", "Legendary", "cryo",
        "GunCodes_pistol.txt")
    named["mislabelled_cryo_but_fire"] = liar
    # the same serial listed twice (search de-duplicates, count() does not)
    row("Liberator", liar, "weapon", "pistol", "Breakfree Arms", "Breakfree Pistol", "Legendary", "fire",
        "GunCodes_pistol.txt")
    # content-pack items: a bounty-pack barrel on a base-game gun (owned by default), a story-pack barrel (not)
    p3 = mk.serial(9101, weapon_parts(rng, 6, "cryo", barrel=21))
    row("Fine Print", p3, "weapon", "pistol", "Breakfree Arms", "Breakfree Pistol", "Legendary", "cryo",
        "GunCodes_pistol.txt")
    named["pack3"] = p3
    st = mk.serial(9112, weapon_parts(rng, 5, "fire", barrel=22))
    row("Loophole", st, "weapon", "shotgun", "Open Vault Co", "Openvault Shotgun", "Legendary", "fire",
        "GunCodes_shotgun.txt")
    named["story"] = st
    # a pearlescent that also carries a plain legendary composition part
    two = mk.serial(9102, weapon_parts(rng, 7, "cryo") + " {5}")
    row("Warranty Void", two, "weapon", "shotgun", "Breakfree Arms", "Breakfree Shotgun", "Pearl", "cryo",
        "GunCodes_shotgun.txt")
    named["pearl_two_comps"] = two
    # an item with two composition parts that is NOT a pearlescent (validate flags it)
    bad = mk.serial(9103, weapon_parts(rng, 5, "fire") + " {4}")
    named["two_comps_not_pearl"] = bad

    for cat, fslug, cname, dbtype, wtype, mfr, src, label, legs in GEAR:
        for comp, leg, rarity in ((5, legs[0], "Legendary"), (6, legs[1], "Legendary"), (7, legs[2], "Pearl")):
            extra = ""
            if dbtype == "repair_kit":
                extra = "{%d:[3 5]} {%d:2}" % (FIRMWARE_CAT, FIRMWARE_CAT)
            s = mk.serial(cat, gear_parts(rng, comp, extra, body_first=(dbtype == "shield")))
            # one shield carries a (hint) element label, so element filters on gear can be exercised
            row(leg, s, dbtype, wtype, mfr, label, rarity,
                "cryo" if (dbtype, comp) == ("shield", 6) else "N/A", src)
            named["%d:%d" % (cat, comp)] = s
        s = mk.serial(cat, gear_parts(rng, 4, body_first=(dbtype == "shield")))
        row("Standard Issue " + label.split()[-1], s, dbtype, wtype, mfr, label, "Epic", "N/A", src)
        if dbtype == "shield":
            # a long tail of plain rares, so listing endpoints can be tested at their page limits (25 / 200)
            for n in range(1, 231):
                s = mk.serial(cat, gear_parts(rng, 3, body_first=True))
                row("Surplus Shield %03d" % n, s, dbtype, wtype, mfr, label, "Rare", "N/A", src)
    for cat, fslug, cname, char, wtype, label, legs in CLASSMODS:
        src = "GunCodes_classmod_%s.txt" % char
        for comp, leg, rarity in ((5, legs[0], "Legendary"), (6, legs[1], "Legendary"), (7, legs[2], "Pearl")):
            s = mk.serial(cat, gear_parts(rng, comp, "{%d:[%d %d]}" % (PERK_CAT, rng.randrange(1, 6),
                                                                      rng.randrange(6, 12))))
            row(leg, s, "classmod", wtype, "Breakfree Arms", label, rarity, "N/A", src)
            named["%d:%d" % (cat, comp)] = s
    return rows, named


def build_known(mk: Maker, named: Dict[str, str]) -> dict:
    """Known answers for the modules' health() checks (the real-data ones are tied to the real game)."""
    codec = mk.codec

    def seed(serial):
        return codec.int_at(codec.decode(serial), 5)

    def op(label, key, cat, rarity, element, leg, others=()):
        sn = named[key]
        return {"label": label, "serial": sn, "category_id": cat, "level": LEVEL, "rarity": rarity,
                "element": element, "legendary_name": leg, "seed": seed(sn),
                "other_components": [list(o) for o in others]}

    kit = named["9202:5"]
    open_vault = named["9102:5"]
    return {
        "_synthetic": MARK,
        "ops": [
            op("weapon (Breakfree SMG, shock)", "9103:5", 9103, "Legendary", "shock", "Free Radical"),
            op("shield (Breakfree Shield, no element)", "9201:5", 9201, "Legendary", None, "Safe Harbor"),
            op("pearlescent (Breakfree Pistol, tagged Pearl)", "9101:7", 9101, "Pearl", "impact", "Skeleton Key"),
            op("pearlescent + legendary component (highest tier governs)", "pearl_two_comps", 9102, "Pearl",
               "cryo", "Warranty Void", (("Legendary", "Open Vault"),)),
        ],
        "rules": {
            "base_serial": named["9101:5"], "story_serial": named["story"], "story_ref": [9112, 22],
            "story_pack": STORY, "bounty_serial": named["pack3"], "bounty_ref": [9101, 21],
            "bounty_pack": PACK3, "two_comps_serial": named["two_comps_not_pearl"],
            "pearl_two_comps_serial": named["pearl_two_comps"], "kit_serial": kit},
        "catalog": {"serial": open_vault, "query": "open vault", "type": "shotgun", "element": "cryo"},
        "builder": {"serial": open_vault, "serial_60": codec.relevel(open_vault, 60), "query": "open vault",
                    "type": "shotgun", "name": "Open Vault", "element": "cryo"},
    }


def build_drops(legs_all) -> dict:
    sources = [("Lord Auditor", "Boss"), ("The Landlord", "Boss"), ("Compliance Officer", "Boss"),
               ("Night Clerk", "Boss")]
    drops = []
    for i, leg in enumerate(legs_all):
        src, typ = sources[i % len(sources)]
        drops.append({"source": src.replace(" ", ""), "source_display": src, "source_type": typ,
                      "manufacturer": "BFA", "gear_type": "WEAPON", "item_name": leg,
                      "item_id": "bfa_weapon.%s" % comp_name(leg), "pool": "itempool_synthetic_%s" % slug(leg),
                      "drop_tier": "Primary" if i % 5 == 0 else "", "drop_chance": 0.06 if i % 5 == 0 else 0.0})
        if i % 3 == 0:
            drops.append({"source": "WorldDrop", "source_display": "World drop", "source_type": "WorldDrop",
                          "manufacturer": "BFA", "gear_type": "WEAPON", "item_name": leg,
                          "item_id": "bfa_weapon.%s" % comp_name(leg), "pool": "itempool_synthetic_world",
                          "drop_tier": "", "drop_chance": 0.02})
    return {"_synthetic": MARK, "version": 1, "drops": drops,
            "probabilities": {"Primary": 0.06, "Secondary": 0.045, "Tertiary": 0.03, "Shiny": 0.01,
                              "TrueBoss": 0.25, "TrueBossShiny": 0.03}}


# ---- writers -----------------------------------------------------------------------------------

def tsv(header: str, rows, comment=True) -> str:
    lines = ["# " + MARK] if comment else []
    lines.append(header)
    lines += ["%s\t%s" % r if len(r) == 2 else "\t".join(str(c) for c in r) for r in rows]
    return "\n".join(lines) + "\n"


def jdump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def build_all() -> Dict[str, str]:
    """relative path -> file text"""
    cats, files, meta, names = build_tables()
    mk = Maker()
    rows, named = build_rows(mk)
    out: Dict[str, str] = {}

    out["manifest/VERSION"] = ("# " + MARK + "\n" + VERSION_LINE + "\n")
    out["manifest/category_names.tsv"] = tsv("category_id\tname", sorted(cats.items()))
    for fname, table in files.items():
        out["manifest/parts/%s.tsv" % fname] = tsv("index\tname", table)
    out["manifest/item_names.tsv"] = "# " + MARK + "\n" + "".join(
        "%s\t%s\n" % kv for kv in sorted(names.items()))
    pm = {"_synthetic": MARK}
    pm.update(dict(sorted(meta.items())))
    out["manifest/part_meta.json"] = jdump(pm)
    legs_all = [l for w in WEAPONS for l in w[6]] + [l for g in GEAR for l in g[8]] + \
               [l for c in CLASSMODS for l in c[6]]
    out["manifest/drops.json"] = jdump(build_drops(legs_all))
    out["manifest/drop_pools.tsv"] = tsv(
        "manufacturer_code\tgear_type_code\tlegendary_count\tboss_source_count\tworld_pool_name",
        [("BFA", "PS", 3, 3, "Pistols"), ("BFA", "SG", 3, 3, "Shotguns"), ("OVC", "SM", 3, 2, "SMGs")])
    out["manifest/manufacturers.json"] = jdump({
        "_synthetic": MARK,
        "BFA": {"code": "BFA", "name": "Breakfree Arms", "path": "synthetic/BFA"},
        "OVC": {"code": "OVC", "name": "Open Vault Co", "path": "synthetic/OVC"}})
    out["manifest/weapon_types.json"] = jdump({
        "_synthetic": MARK,
        "PS": {"name": "Pistol", "path": "synthetic/Pistol", "manufacturers": [
            {"code": "BFA", "name": "Breakfree Arms"}, {"code": "OVC", "name": "Open Vault Co"}]}})
    out["manifest/gear_types.json"] = jdump({
        "_synthetic": MARK,
        "Shield": {"name": "Shield", "path": "synthetic/Shield", "manufacturers": [
            {"code": "BFA", "name": "Breakfree Arms"}]}})
    out["manifest/known_answers.json"] = jdump(build_known(mk, named))
    out["bl4-serial-matches.json"] = jdump(rows)
    out["named-serials.json"] = jdump({"_synthetic": MARK, "serials": named})
    out["README.md"] = (
        "# SYNTHETIC — not game data\n\n"
        "This folder is a made-up dataset in the same file layout the program reads from a real\n"
        "extract. Every manufacturer, item, part, category id and serial in it is invented (the\n"
        "serials were produced by this repo's own codec, so they decode, but they are not real\n"
        "items). It exists so the tests and the demo work with nothing else installed.\n\n"
        "Regenerate with `python scripts/make_synthetic.py` (deterministic). To use your own real\n"
        "tables instead, build them with `python scripts/build_data.py` (see docs/runbooks/USER.md).\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "data" / "synthetic"), help="folder to write")
    ap.add_argument("--check", action="store_true", help="do not write; exit 1 if files differ")
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    files = build_all()
    if args.check:
        bad = [rel for rel, text in files.items()
               if not (out_dir / rel).is_file() or (out_dir / rel).read_bytes() != text.encode("utf-8")]
        for rel in bad:
            print("differs or missing:", rel)
        return 1 if bad else 0
    for rel, text in files.items():
        p = out_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    print("wrote %d files under %s" % (len(files), out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
