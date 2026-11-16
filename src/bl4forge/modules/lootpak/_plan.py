"""The planner: config + base files -> an explicit list of `set_leaf` operations. Writes nothing but scratch.

v1 supports ONE operation, `set_leaf`: retarget one existing leaf to a string that is already in the value pool.
Inserting a struct or a leaf and adding pool strings are not planned (they error clearly): inserting
rarity_modifier into Normal stopped Normal drops in game, so the builder does not offer it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple

from ...core.errors import ConfigError, LootPakError
from ._config import SECTIONS, LootConfig, format_value
from ._decode import DTable, find_table, parse_decode
from ._leaves import pool_index
from ._locate import locate
from ._tools import Tools


@dataclass(frozen=True)
class Change:
    op: str                 # always "set_leaf" in v1
    label: str              # section.Row.field (row as named in the base)
    table: str
    row: str
    path: str
    bitpos: int
    bits: int
    old_index: int
    new_index: int
    old_text: str
    new_text: str
    line: int               # 0-based decode line that must change
    prefix: str             # decode line text before the value

    @property
    def triple(self) -> Tuple[int, int, int, int]:
        return (self.bitpos, self.bits, self.old_index, self.new_index)

    @property
    def old_line(self) -> str:
        return self.prefix + self.old_text

    @property
    def new_line(self) -> str:
        return self.prefix + self.new_text

    def as_dict(self) -> Dict[str, object]:
        return {"op": self.op, "label": self.label, "table": self.table, "row": self.row, "field": self.path,
                "bitpos": self.bitpos, "bits": self.bits, "old_index": self.old_index,
                "new_index": self.new_index, "old": self.old_text, "new": self.new_text,
                "decode_line": self.line + 1}


@dataclass
class Plan:
    name: str
    binoff: int
    changes: Tuple[Change, ...]
    unchanged: Tuple[str, ...]               # labels already at the requested value
    notes: Tuple[str, ...]
    base_decode: str = field(repr=False, default="")


def format_plan(plan: Plan) -> List[str]:
    out = ["plan %s: %d set_leaf change(s), %d already at target" % (plan.name, len(plan.changes), len(plan.unchanged))]
    for c in plan.changes:
        out.append("  set_leaf %-56s %12s -> %-12s bit %d (%db)  pool %d -> %d"
                   % (c.label, c.old_text, c.new_text, c.bitpos, c.bits, c.old_index, c.new_index))
    for lab in plan.unchanged:
        out.append("  keep     %s (already the requested value)" % lab)
    for n in plan.notes:
        out.append("  note: %s" % n)
    return out


def _find_row(table: DTable, key: str, section: str, wanted: str):
    hits = [r for r in table.rows if r.name.lower() == wanted.lower()]
    if len(hits) != 1:
        names = ", ".join(r.name for r in table.rows[:40])
        raise ConfigError("[%s] unknown row %r in %s; rows: %s" % (section, wanted, key, names))
    return hits[0]


def make_plan(config: LootConfig, tools: Tools, work: Path) -> Plan:
    """Decode the base, resolve every named row/field, snap values to the pool, locate the leaves."""
    work.mkdir(parents=True, exist_ok=True)
    base_ncs = work / "base.ncs"
    tools.wrap(config.base.raw, base_ncs)
    base_decode = tools.decode(base_ncs)
    tables = parse_decode(base_decode)

    resolved: List[Tuple[object, str, str, str]] = []        # setting, table key, canonical row, path
    targets: Dict[str, Set[str]] = {}
    for s in config.settings:
        tkey = SECTIONS[s.section][0]
        table = find_table(tables, tkey)
        row = _find_row(table, tkey, s.section, s.row)
        if row.get(s.field) is None:
            have = ", ".join(lf.path for lf in row.leaves) or "no fields"
            raise ConfigError("[%s.%s] the base row has no field %r (v1 never inserts a leaf or struct); it has: %s"
                              % (s.section, row.name, s.field, have))
        resolved.append((s, tkey, row.name, s.field))
        targets.setdefault(tkey, set()).add(row.name)

    located, log, pool = locate(tools, work / "probe", config.base.raw, base_decode,
                                {k: sorted(v) for k, v in targets.items()})
    index = pool_index(pool)
    changes: List[Change] = []
    unchanged: List[str] = []
    notes: List[str] = []
    for s, tkey, rname, path in resolved:
        label = "%s.%s.%s" % (s.section, rname, path)
        text = format_value(s.value)
        idxs = index.get(text)
        if not idxs:
            raise ConfigError("%s = %s is not in the string pool; add-strings is not available in v1 "
                              "(pick a value that already exists, e.g. a number another row uses)" % (label, text))
        if len(idxs) > 1:
            notes.append("%s: %r is in the pool %d times; using the lowest index %d" % (label, text, len(idxs), idxs[0]))
        loc = located[(tkey, rname, path)]
        if not loc.consistent:
            raise LootPakError("%s: the located leaf holds %r but the decode says %r; refusing to edit it"
                               % (label, loc.leaf.val, loc.dleaf.value))
        if loc.leaf.raw in idxs:                  # same string already (a pool can hold a string twice): no change
            unchanged.append(label)
            continue
        new = idxs[0]
        if new >= (1 << loc.leaf.bits):
            raise LootPakError("%s: pool index %d does not fit the leaf's %d bits" % (label, new, loc.leaf.bits))
        if new == loc.leaf.raw:
            unchanged.append(label)
            continue
        changes.append(Change("set_leaf", label, tkey, rname, path, loc.leaf.bitpos, loc.leaf.bits, loc.leaf.raw,
                              new, loc.dleaf.value, text, loc.dleaf.line, loc.dleaf.prefix))
    changes.sort(key=lambda c: c.bitpos)
    if len({c.bitpos for c in changes}) != len(changes):
        raise LootPakError("two planned changes hit the same leaf")
    return Plan(config.name, log.binoff, tuple(changes), tuple(unchanged), tuple(notes), base_decode)
