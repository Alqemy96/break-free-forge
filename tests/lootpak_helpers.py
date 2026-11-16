"""A fake `Tools` for the loot-pak tests: it stands in for ncstool, bl4 and uextract with an in-memory model.

A fake "raw table" is JSON: a value pool, the leaves in BINARY order (bit position, width, pool index) and a
layout saying which leaf each decoded field is, in DECODE (alphabetical) order. The binary order is deliberately
NOT the decode order (the six *_probability leaves are classmods, enhancements, repkits, grenadesorgadgets,
shields, guns), exactly like the real file, so a planner that trusts decode order fails these tests.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from bl4forge.core.errors import LootPakError
from bl4forge.modules.lootpak._tools import Tools

BINOFF = 777
PROBS_BINARY = ["classmods_probability", "enhancements_probability", "repkits_probability",
                "grenadesorgadgets_probability", "shields_probability", "guns_probability"]
RARITY = [("commonmodifier", "0.750000"), ("uncommonmodifier", "5.000000"), ("raremodifier", "15.000000"),
          ("veryraremodifier", "7.000000"), ("legendarymodifier", "5.000000"), ("pearlmodifier", "5.000000")]

VALUES = ["0.000000", "0.050000", "0.100000", "0.150000", "0.200000", "0.250000", "0.400000", "0.600000",
          "0.700000", "0.750000", "0.005000", "0.012000", "0.040000", "1.000000", "1.500000", "4.000000",
          "5.000000", "7.000000", "8.000000", "9.000000", "15.000000", "25.000000", "100.000000", "-0.250000"]
WORDS = ["Table_EnemyDrops", "/Game/Struct_EnemyDrops.Struct_EnemyDrops", "Chump", "Normal", "Elite",
         "Rarity_Balance", "/Game/Struct_Balance_Rarity.Struct_Balance_Rarity", "Common", "UnCommon",
         "Att_LocalRarityModifier_01_Common", "Att_LocalRarityModifier_02_Uncommon",
         "Table_Difficulty_Standard", "/Game/Struct_Difficulty.Struct_Difficulty", "Easy", "Easy_junk", "junk"]
FILLER = ["%d.250000" % i for i in range(1000, 1200)]          # sentinel fodder for the probe
# appended AFTER the filler so no earlier pool index moves
SPAWN_WORDS = ["Table_PlayerCountSpawnBalanceData", "/Script/OakGame.PlayerCountDefinedValueRow", "true", "none",
               "None", "SoloDefault", "Duo_add1", "no modification", "add one", "2.000000", "3.000000"]
SPAWN_ROWS = {"SoloDefault": ("0.000000", "no modification"), "Duo_add1": ("1.000000", "add one")}
MAPS_BINARY = ["oneplayer", "twoplayers", "threeplayers", "fourplayers"]    # decode order is alphabetical
# per map, binary order: constant, attribute, datatablevalue.{columnname, rowname, datatable}, postscale


def make_pool() -> List[str]:
    return VALUES + WORDS + FILLER + SPAWN_WORDS


def make_raw(overrides: Optional[Dict[Tuple[str, str], str]] = None) -> bytes:
    """Build the fake raw table. `overrides[(row, field)] = value text` seeds different starting values."""
    ov = overrides or {}
    pool = make_pool()
    leaves: List[Dict[str, int]] = []
    tables: List[dict] = []

    def leaf(text: str) -> int:
        leaves.append({"bitpos": 100 + 30 * len(leaves), "bits": 13, "raw": pool.index(text)})
        return len(leaves) - 1

    leaf("junk")
    # ---- enemydrops: decode order alphabetical, binary order per the real file ----
    rows = []
    start = {"Chump": ("0.050000", "0.200000"), "Normal": ("0.050000", "1.500000"), "Elite": ("0.100000", "4.000000")}
    anchor = [leaf("Table_EnemyDrops"), leaf("/Game/Struct_EnemyDrops.Struct_EnemyDrops")]
    for rname, (prob, exp) in start.items():
        name_leaf = leaf(rname)
        fields: Dict[str, int] = {}
        if rname == "Elite":
            for f, v in RARITY:
                fields["rarity_modifier." + f] = leaf(ov.get((rname, "rarity_modifier." + f), v))
        for f in PROBS_BINARY:
            fields[f] = leaf(ov.get((rname, f), prob))
        fields["exp_multiplier"] = leaf(ov.get((rname, "exp_multiplier"), exp))
        fields["currencyorammo_probability"] = leaf("0.750000")
        rows.append({"name": rname, "name_leaf": name_leaf, "fields": sorted(fields.items())})
    tables.append({"key": "table_enemydrops", "name": "Table_EnemyDrops",
                   "struct": "/Game/Struct_EnemyDrops.Struct_EnemyDrops", "rows": rows})
    # ---- rarity_balance: binary order local_modifier, base_weight, growth_exponent ----
    rows = []
    leaf("Rarity_Balance"), leaf("/Game/Struct_Balance_Rarity.Struct_Balance_Rarity")
    for rname, bw, att in (("Common", "0.050000", "Att_LocalRarityModifier_01_Common"),
                           ("UnCommon", "0.040000", "Att_LocalRarityModifier_02_Uncommon")):
        name_leaf = leaf(rname)
        fields = {"local_modifier": leaf(att), "base_weight": leaf(ov.get((rname, "base_weight"), bw)),
                  "growth_exponent": leaf("0.000000")}
        rows.append({"name": rname, "name_leaf": name_leaf, "fields": sorted(fields.items())})
    tables.append({"key": "rarity_balance", "name": "Rarity_Balance",
                   "struct": "/Game/Struct_Balance_Rarity.Struct_Balance_Rarity", "rows": rows})
    # ---- difficulty standard: Easy has no lootluck, Normal has ----
    rows = []
    leaf("Table_Difficulty_Standard"), leaf("/Game/Struct_Difficulty.Struct_Difficulty")
    n1 = leaf("Easy")
    rows.append({"name": "Easy", "name_leaf": n1, "fields": [("damagetaken", leaf("-0.250000"))]})
    n2 = leaf("Normal")
    rows.append({"name": "Normal", "name_leaf": n2,
                 "fields": [("lootluck", leaf(ov.get(("Normal", "lootluck"), "100.000000")))]})
    tables.append({"key": "table_difficulty_standard", "name": "Table_Difficulty_Standard",
                   "struct": "/Game/Struct_Difficulty.Struct_Difficulty", "rows": rows})
    # ---- Table_PlayerCountSpawnBalanceData: nested maps, non-float leaves, and an always_loaded 'true' leaf
    # between the row-struct leaf and the first row name (as in the real file) ----
    rows = []
    leaf("Table_PlayerCountSpawnBalanceData"), leaf("/Script/OakGame.PlayerCountDefinedValueRow"), leaf("true")
    for rname, (const, comment) in SPAWN_ROWS.items():
        name_leaf = leaf(rname)
        fields = {}
        for m in MAPS_BINARY:
            fields[m + ".constant"] = leaf(ov.get((rname, m + ".constant"), const))
            fields[m + ".attribute"] = leaf("none")
            fields[m + ".datatablevalue.columnname"] = leaf("None")
            fields[m + ".datatablevalue.rowname"] = leaf("None")
            fields[m + ".datatablevalue.datatable"] = leaf("none")
            fields[m + ".postscale"] = leaf("1.000000")
        fields["comment"] = leaf(comment)
        rows.append({"name": rname, "name_leaf": name_leaf, "fields": sorted(fields.items())})
    tables.append({"key": "table_playercountspawnbalancedata", "name": "Table_PlayerCountSpawnBalanceData",
                   "struct": "/Script/OakGame.PlayerCountDefinedValueRow", "rows": rows, "always_loaded": True})
    return json.dumps({"binoff": BINOFF, "pool": pool, "leaves": leaves, "tables": tables}).encode()


def _val(model: dict, i: int) -> str:
    return model["pool"][model["leaves"][i]["raw"]]


def render_decode(model: dict, path: str = "fake") -> str:
    out = ["File: %s" % path, "Tables: 1", "", "--- Table: gbx_ue_data_table ---", "  Records: 1", "",
           "  Record 0:", "    Tags: a=base b=1"]
    for t in model["tables"]:
        out.append("    %s = {" % t["key"])
        if t.get("always_loaded"):
            out.append("      always_loaded_struct: true")
        out.append("      data: [{")
        for n, row in enumerate(t["rows"]):
            if n:
                out.append("        }, {")
            out.append("          row_name: %s" % _val(model, row["name_leaf"]))
            out.append("          row_value: {")
            stack: List[str] = []
            for fpath, li in row["fields"]:
                text = _val(model, li)
                parts = fpath.split(".")
                if parts[-1] == "local_modifier" or parts[-1] == "attribute":
                    text = "attribute'%s'" % text
                elif parts[-1] == "datatable":
                    text = "gbx_ue_data_table'%s'" % text
                groups = parts[:-1]
                while stack and stack != groups[:len(stack)]:
                    stack.pop()
                    out.append("%s}" % ("            " + "  " * len(stack)))
                for g in groups[len(stack):]:
                    out.append("%s%s: {" % ("            " + "  " * len(stack), g))
                    stack.append(g)
                out.append("%s%s: %s" % ("            " + "  " * len(stack), parts[-1], text))
            while stack:
                stack.pop()
                out.append("%s}" % ("            " + "  " * len(stack)))
            out.append("          }")
        out.append("        }]")
        out.append("      gbx_ue_data_table: %s" % t["name"])
        out.append("      row_struct: Asset'%s'" % t["struct"])
        out.append("    }")
    return "\n".join(out) + "\n"


class FakeTools(Tools):
    """Records every call in `calls`. `sneak_change` makes set-bits (real builds only, not probes) also change
    one leaf nobody asked for, so the decode-diff gate has something to catch."""

    def __init__(self, sneak_change: bool = False):
        self.calls: List[Tuple[str, tuple]] = []
        self.sneak_change = sneak_change

    # raw files hold the JSON model; "ncs" files hold b"FAKE" + the same JSON
    @staticmethod
    def _load(path: Path) -> dict:
        data = Path(path).read_bytes()
        if data.startswith(b"FAKE"):
            data = data[4:]
        return json.loads(data)

    def leaves(self, raw: Path) -> str:
        self.calls.append(("leaves", (Path(raw).name,)))
        m = self._load(raw)
        out = ["BINOFF %d" % m["binoff"], "REMAPB count=0 vbw=0 ibw=0 values=[]"]
        for lf in m["leaves"]:
            out.append("LEAF bitpos=%d bits=%d raw=%d mapped=%d val=%s"
                       % (lf["bitpos"], lf["bits"], lf["raw"], lf["raw"], m["pool"][lf["raw"]]))
        return "\n".join(out) + "\n"

    def strings(self, raw: Path) -> str:
        self.calls.append(("strings", (Path(raw).name,)))
        return "\n".join("%d\t%s" % (i, s) for i, s in enumerate(self._load(raw)["pool"])) + "\n"

    def set_bits(self, src: Path, dst: Path, binoff: int, triples: Sequence[Tuple[int, int, int, int]]) -> str:
        self.calls.append(("set_bits", (Path(dst).name, binoff, tuple(triples))))
        m = self._load(src)
        if binoff != m["binoff"]:
            raise LootPakError("fake set-bits: wrong BINOFF %d" % binoff)
        by_pos = {lf["bitpos"]: lf for lf in m["leaves"]}
        for bitpos, bits, old, new in triples:
            lf = by_pos.get(bitpos)
            if lf is None or lf["bits"] != bits or lf["raw"] != old:
                raise LootPakError("fake set-bits: old index mismatch at bit %d" % bitpos)
            if new >= (1 << bits):
                raise LootPakError("fake set-bits: new index too wide")
            lf["raw"] = new
        if self.sneak_change and not Path(dst).name.startswith("probe"):
            row = [r for t in m["tables"] if t["key"] == "table_enemydrops" for r in t["rows"] if r["name"] == "Chump"][0]
            li = dict(row["fields"])["currencyorammo_probability"]
            m["leaves"][li]["raw"] = m["pool"].index("1.000000")
        Path(dst).write_bytes(json.dumps(m).encode())
        return "ok"

    def wrap(self, raw: Path, ncs: Path) -> None:
        self.calls.append(("wrap", (Path(raw).name, Path(ncs).name)))
        Path(ncs).write_bytes(b"FAKE" + Path(raw).read_bytes())

    def decode(self, ncs: Path) -> str:
        self.calls.append(("decode", (Path(ncs).name,)))
        return render_decode(self._load(ncs), str(ncs))

    def mkpak(self, out: Path, mount: str, seed: Optional[int], reference_pak: Path, entries) -> None:
        self.calls.append(("mkpak", (Path(out).name, mount, seed, Path(reference_pak).name,
                                     tuple(n for n, _ in entries))))
        Path(out).write_text(json.dumps({n: Path(p).read_bytes().hex() for n, p in entries}), encoding="utf-8")

    def extract(self, pak: Path, out_dir: Path) -> List[Path]:
        self.calls.append(("extract", (Path(pak).name,)))
        files = []
        for name, hexdata in json.loads(Path(pak).read_text(encoding="utf-8")).items():
            p = Path(out_dir) / Path(pak).stem / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(bytes.fromhex(hexdata))
            files.append(p)
        return sorted(files)

    def fingerprints(self) -> Dict[str, str]:
        return {"ncstool": "fake", "bl4": "fake", "uextract": "fake"}

    def commands(self) -> Dict[str, str]:
        return {"ncstool": "ncstool", "bl4": "bl4", "uextract": "uextract"}


def write_base(root: Path, overrides=None) -> Dict[str, Path]:
    """Write the fake base files under root/base and return their paths."""
    base = Path(root) / "base"
    base.mkdir(parents=True, exist_ok=True)
    raw, inv, ref = base / "t0.raw", base / "inv.ncs", base / "ref.pak"
    raw.write_bytes(make_raw(overrides))
    inv.write_bytes(b"inventory-bytes")
    ref.write_bytes(b"reference-pak")
    return {"raw": raw, "inventory": inv, "reference_pak": ref}


def config_text(paths: Dict[str, Path], body: str, name: str = "t") -> str:
    q = lambda p: str(p).replace("\\", "/")
    return ('[meta]\nname = "%s"\n[base]\nraw = "%s"\ninventory = "%s"\nreference_pak = "%s"\n%s'
            % (name, q(paths["raw"]), q(paths["inventory"]), q(paths["reference_pak"]), body))
