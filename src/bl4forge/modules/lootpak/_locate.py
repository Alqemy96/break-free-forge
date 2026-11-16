"""Find the bit position of every leaf of the rows we are asked to edit, by STRUCTURE, never by constant.

Two independent sources are joined:
  * the leaf log (`NCS_LEAFLOG=1 ncstool leaves`): every leaf of the file in BINARY order, with bit position;
  * the decode (`bl4 ncs show`): the same leaves with field names, in ALPHABETICAL order within a struct.
The binary order inside a struct is not the decode order (in table_enemydrops the six *_probability leaves are
classmods, enhancements, repkits, grenadesorgadgets, shields, guns), so order is never trusted. Instead:

 1. a row's leaves are a window of the log: the table is anchored by its table name leaf, followed by the row
    struct leaf, then each row name leaf and exactly as many leaves as the row has in the decode;
 2. the window's leaves are overwritten with distinct sentinel pool strings in a SCRATCH copy, that copy is
    decoded, and the decode lines that changed say which field each leaf is.

The mapping is cross-checked: a leaf's original string must equal the decoded value of its field (`consistent`;
the planner refuses an edit of a leaf that is not).
"""
from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Set, Tuple

from ...core.errors import LootPakError
from ._decode import DLeaf, DRow, DTable, diff_lines, find_table, normalise, parse_decode, strip_wrapper
from ._leaves import Leaf, LeafLog, parse_leaf_log, parse_pool
from ._tools import Tools

_FLOAT = re.compile(r"-?\d+\.\d{6}")
_FLOAT_FULL = re.compile(r"^-?\d+\.\d{6}$")


@dataclass(frozen=True)
class Located:
    table: str
    row: str
    path: str
    leaf: Leaf          # bit position, width, pool index, string
    dleaf: DLeaf        # decode line (for the gate)
    consistent: bool    # the leaf's own string equals the decoded value of its field


def row_windows(log: LeafLog, table: DTable) -> Dict[str, Tuple[int, int]]:
    """row name -> (index of its first value leaf in log.leaves, number of leaves). Raises when the shape
    does not match (so a table we do not understand is refused rather than guessed)."""
    if not table.rows or not table.table_name:
        raise LootPakError("table %r has no rows/name in the decode" % table.key)
    first = table.rows[0].name
    struct_tail = table.row_struct.split("'")[1] if "'" in table.row_struct else table.row_struct
    leaves = log.leaves
    anchors = []
    for i in range(len(leaves) - 2):
        if leaves[i].val != table.table_name or leaves[i + 1].val != struct_tail:
            continue
        # some tables carry a boolean leaf (always_loaded_struct) between the struct leaf and the first row
        # name; skip booleans only (at most two), anything else is a shape we do not understand
        j = i + 2
        while j < len(leaves) - 1 and j - (i + 2) < 2 and leaves[j].val in ("true", "false") and leaves[j].val != first:
            j += 1
        if leaves[j].val == first:
            anchors.append(j)
    if len(anchors) != 1:
        raise LootPakError("cannot anchor table %r in the leaf log (%d candidates for %r + %r + %r)"
                           % (table.key, len(anchors), table.table_name, struct_tail, first))
    pos = anchors[0]                           # index of the first row-name leaf
    out: Dict[str, Tuple[int, int]] = {}
    for row in table.rows:
        if pos >= len(leaves) or leaves[pos].val != row.name:
            raise LootPakError("table %r: expected row-name leaf %r at leaf #%d, found %r"
                               % (table.key, row.name, pos, leaves[pos].val if pos < len(leaves) else None))
        if row.name in out:
            raise LootPakError("table %r has two rows named %r; refusing to guess" % (table.key, row.name))
        out[row.name] = (pos + 1, len(row.leaves))
        pos += 1 + len(row.leaves)
    return out


def _sentinels(pool: Mapping[int, str], leaves: List[Leaf]) -> List[int]:
    """One distinct float-looking pool index per leaf, never the leaf's own value, that fits its bit width."""
    floats = [i for i in sorted(pool) if _FLOAT_FULL.match(pool[i])]
    out: List[int] = []
    used: Set[int] = set()
    it = iter(floats)
    for lf in leaves:
        for idx in it:
            if idx != lf.raw and idx not in used and idx < (1 << lf.bits):
                used.add(idx)
                out.append(idx)
                break
        else:
            raise LootPakError("not enough float strings in the pool to probe %d leaves" % len(leaves))
    return out


def locate(tools: Tools, work: Path, raw: Path, base_decode: str,
           targets: Mapping[str, Iterable[str]]) -> Tuple[Dict[Tuple[str, str, str], Located], LeafLog, Dict[int, str]]:
    """Locate every leaf of `targets` (table key -> row names) in `raw`. `work` is a scratch folder.
    Returns ({(table, row, path): Located}, the leaf log, the pool)."""
    log = parse_leaf_log(tools.leaves(raw))
    pool = parse_pool(tools.strings(raw))
    tables = parse_decode(base_decode)
    probe_leaves: List[Leaf] = []
    owners: List[Tuple[str, str, Leaf]] = []                # (table, row, leaf) per probed leaf
    row_lines: Dict[Tuple[str, str], Dict[int, DLeaf]] = {}  # decode lines each probed row owns
    for tkey, rows in targets.items():
        table = find_table(tables, tkey)
        windows = row_windows(log, table)
        by_name = {r.name: r for r in table.rows}
        for rname in rows:
            if rname not in windows:
                raise LootPakError("table %r has no row %r" % (tkey, rname))
            start, count = windows[rname]
            row: DRow = by_name[rname]
            row_lines[(tkey, rname)] = {dl.line: dl for dl in row.leaves}
            for k in range(count):
                lf = log.leaves[start + k]
                probe_leaves.append(lf)
                owners.append((tkey, rname, lf))
    if not owners:
        return {}, log, pool
    sentinels = _sentinels(pool, probe_leaves)
    work.mkdir(parents=True, exist_ok=True)
    probe_raw, probe_ncs = work / "probe.raw", work / "probe.ncs"
    tools.set_bits(raw, probe_raw, log.binoff, [(lf.bitpos, lf.bits, lf.raw, s) for lf, s in zip(probe_leaves, sentinels)])
    tools.wrap(probe_raw, probe_ncs)
    changed = diff_lines(base_decode, tools.decode(probe_ncs))
    by_sentinel: Dict[str, int] = {}
    for n, s in enumerate(sentinels):
        by_sentinel[pool[s]] = n
    line_to_leaf: Dict[int, int] = {}
    for line_no, _old, new in changed:
        m = _FLOAT.search(new.split(": ", 1)[-1])
        n = by_sentinel.get(m.group(0)) if m else None
        if n is None:
            raise LootPakError("probe: decode line %d changed to something that is not a sentinel: %r" % (line_no + 1, new))
        if n in line_to_leaf.values():
            raise LootPakError("probe: a sentinel appears on two decode lines (line %d)" % (line_no + 1))
        line_to_leaf[line_no] = n
    leaf_to_line = {n: ln for ln, n in line_to_leaf.items()}
    result: Dict[Tuple[str, str, str], Located] = {}
    for n, (tkey, rname, lf) in enumerate(owners):
        ln = leaf_to_line.get(n)
        dl = row_lines[(tkey, rname)].get(ln) if ln is not None else None
        if dl is None:
            raise LootPakError("probe: the leaf at bit %d (%s.%s) changed no decode line of its own row (line %s); the "
                               "row's layout is not what the decode says" % (lf.bitpos, tkey, rname, ln))
        result[(tkey, rname, dl.path)] = Located(tkey, rname, dl.path, lf, dl, strip_wrapper(dl.value) == lf.val)
    # the probe leaves are exactly the changed lines: nothing else moved
    if len(line_to_leaf) != len(owners):
        raise LootPakError("probe changed %d decode lines for %d probed leaves" % (len(line_to_leaf), len(owners)))
    return result, log, pool


def scratch_dir():
    return tempfile.TemporaryDirectory(prefix="lootpak-")
