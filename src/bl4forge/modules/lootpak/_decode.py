"""Parse the text printed by `bl4 ncs show` into table -> row -> scalar leaves (with their line numbers).

Only the `data: [{ row_name / row_value }]` shape is read. Every scalar under a `row_value` is a leaf,
addressed by a dotted path such as `rarity_modifier.commonmodifier` or `guns_howmany.chances[0].chance.constant`.
Line numbers are 0-based indexes into `text.split("\\n")` (line 0 is the `File:` line, which differs per run).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ...core.errors import LootPakError

_OPEN = re.compile(r"^(?P<key>[^\s:=]+)(?: = |: )(?P<br>\[, \{|\[\{|\{)$")
_SCALAR = re.compile(r"^(?P<key>[^\s:=]+): (?P<val>.*)$")


@dataclass(frozen=True)
class DLeaf:
    line: int          # 0-based index into the decode lines
    path: str          # dotted path inside row_value
    prefix: str        # the line up to and including "key: " (so a new line = prefix + new value)
    value: str         # value text exactly as printed


@dataclass
class DRow:
    name: str
    leaves: List[DLeaf] = field(default_factory=list)

    def get(self, path: str) -> Optional[DLeaf]:
        for lf in self.leaves:
            if lf.path == path:
                return lf
        return None


@dataclass
class DTable:
    key: str                       # e.g. "table_enemydrops"
    table_name: str = ""           # gbx_ue_data_table: Table_EnemyDrops
    row_struct: str = ""
    rows: List[DRow] = field(default_factory=list)


def normalise(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def strip_wrapper(value: str) -> str:
    """`attribute'X'` -> `X` (the leaf log carries the bare string)."""
    m = re.fullmatch(r"[A-Za-z_]+'(.*)'", value)
    return m.group(1) if m else value


def parse_decode(text: str) -> Dict[str, List[DTable]]:
    """table key -> every table with that key (normally one). Raises LootPakError on unbalanced braces."""
    lines = normalise(text).split("\n")
    tables: Dict[str, List[DTable]] = {}
    frames: List[list] = []                  # [key, array_index_or_None]
    cur: Optional[DTable] = None
    row: Optional[DRow] = None
    for no, raw in enumerate(lines):
        s = raw.strip()
        if not s:
            continue
        if s == "}, {":
            if not frames or frames[-1][1] is None:
                raise LootPakError("decode line %d: '}, {' outside an array" % (no + 1))
            frames[-1][1] += 1
            if len(frames) == 2 and frames[1][0] == "data" and cur is not None:
                row = DRow("")
                cur.rows.append(row)
            continue
        if s in ("}]", "}, ]", "}"):
            if not frames:
                continue                      # a close we never opened (header noise)
            frames.pop()
            if len(frames) <= 1:
                row = None
            if not frames:
                cur = None
            continue
        m = _OPEN.match(s)
        if m:
            key, br = m.group("key"), m.group("br")
            arr = br != "{"
            if not frames:
                if not arr and " = " in s:
                    cur = DTable(key=key)
                    tables.setdefault(key, []).append(cur)
                    frames.append([key, None])
                continue                      # some other top-level block we do not read
            frames.append([key, (1 if br == "[, {" else 0) if arr else None])
            if arr and len(frames) == 2 and key == "data" and cur is not None:
                row = DRow("")
                cur.rows.append(row)
            continue
        m = _SCALAR.match(s)
        if m and frames and cur is not None:
            key, val = m.group("key"), m.group("val")
            depth = len(frames)
            if depth == 1:                    # table-level scalars
                if key == "gbx_ue_data_table":
                    cur.table_name = val
                elif key == "row_struct":
                    cur.row_struct = val
            elif depth == 2 and frames[1][0] == "data" and key == "row_name" and row is not None:
                row.name = val
            elif depth >= 3 and frames[1][0] == "data" and frames[2][0] == "row_value" and row is not None:
                parts = []
                for fr in frames[3:]:
                    parts.append(fr[0] if fr[1] is None else "%s[%d]" % (fr[0], fr[1]))
                parts.append(key)
                prefix = raw[: len(raw) - len(raw.lstrip())] + key + ": "
                row.leaves.append(DLeaf(no, ".".join(parts), prefix, val))
    if frames:
        raise LootPakError("decode text ends inside an unclosed block (%s)" % ".".join(str(f[0]) for f in frames))
    return tables


def find_table(tables: Dict[str, List[DTable]], key: str) -> DTable:
    hits = tables.get(key, [])
    if not hits:
        raise LootPakError("table %r not found in the base decode" % key)
    if len(hits) != 1:
        raise LootPakError("table %r appears %d times in the base decode; refusing to guess" % (key, len(hits)))
    return hits[0]


def diff_lines(base: str, new: str) -> List[Tuple[int, str, str]]:
    """(line index, old, new) for every differing line; line 0 (`File:`) is skipped. The two texts must have
    the same number of lines (a value edit never adds or removes a line)."""
    a, b = normalise(base).split("\n"), normalise(new).split("\n")
    if len(a) != len(b):
        raise LootPakError("decode line count changed: %d -> %d" % (len(a), len(b)))
    return [(i, a[i], b[i]) for i in range(1, len(a)) if a[i] != b[i]]
