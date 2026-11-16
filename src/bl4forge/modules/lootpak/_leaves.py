"""Parse `NCS_LEAFLOG=1 ncstool leaves <raw>` (stderr) and `ncstool strings <raw>` (stdout)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from ...core.errors import LootPakError

_LEAF = re.compile(r"^LEAF bitpos=(\d+) bits=(\d+) raw=(\d+) mapped=(\d+) val=(.*)$")
_BINOFF = re.compile(r"^BINOFF (\d+)$")
_POOL = re.compile(r"^(\d+)\t(.*)$")


@dataclass(frozen=True)
class Leaf:
    bitpos: int
    bits: int
    raw: int          # pool index
    val: str


@dataclass(frozen=True)
class LeafLog:
    binoff: int
    leaves: Tuple[Leaf, ...]


def parse_leaf_log(text: str) -> LeafLog:
    binoff = None
    leaves: List[Leaf] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        m = _BINOFF.match(line)
        if m:
            binoff = int(m.group(1))
            continue
        m = _LEAF.match(line)
        if m:
            if m.group(3) != m.group(4):
                raise LootPakError("leaf at bit %s is remapped (raw %s, mapped %s): remap tables are not "
                                   "supported in v1" % (m.group(1), m.group(3), m.group(4)))
            leaves.append(Leaf(int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(5)))
    if binoff is None or not leaves:
        raise LootPakError("no BINOFF/LEAF lines in the leaf log (was NCS_LEAFLOG=1 set and the table parsed?)")
    return LeafLog(binoff, tuple(leaves))


def parse_pool(text: str) -> Dict[int, str]:
    pool: Dict[int, str] = {}
    for line in text.replace("\r\n", "\n").split("\n"):
        m = _POOL.match(line)
        if m:
            pool[int(m.group(1))] = m.group(2)
    if not pool:
        raise LootPakError("empty string pool from `ncstool strings`")
    return pool


def pool_index(pool: Dict[int, str]) -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = {}
    for i in sorted(pool):
        out.setdefault(pool[i], []).append(i)
    return out
