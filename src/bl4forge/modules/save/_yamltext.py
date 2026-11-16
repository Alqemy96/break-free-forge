"""Line-level editing of a save's YAML, as TEXT. Nothing here parses YAML into objects or dumps it back.

The game's YAML has no integrity field, but a re-serialiser (bl4.exe `set`) changes ~226 lines of
formatting. So we scan the text with an indentation-aware path tracker, find the one line we want and
replace only its VALUE. Every other byte, including line endings and `key: ` trailing spaces, is kept.
"""
from __future__ import annotations

import difflib
import re
from typing import Dict, List, NamedTuple, Optional, Tuple

from ...core.errors import SaveError
from ...core.types import SaveItem

_KEY_LINE = re.compile(r"^(?P<indent> *)(?P<dash>- +)?(?P<key>[A-Za-z0-9_.\-]+):(?P<sep> *)(?P<value>.*)$")
_DASH_LINE = re.compile(r"^(?P<indent> *)- ")
_INT = re.compile(r"^[+-]?\d+$")
_SERIAL_OK = re.compile(r"^@U[\x21-\x7e]+$")      # printable ASCII, no spaces: how every real serial looks

AREAS = ("backpack", "equipped", "lostloot")
MAX_CURRENCY = 2 ** 63 - 1                          # the largest value that cannot overflow an int64
LEVEL_MIN, LEVEL_MAX = 1, 100
MAX_POINTS = 2 ** 31 - 1


class Rec(NamedTuple):
    idx: int                  # 0-based index into the line list
    path: Tuple[str, ...]     # container names above the key ("-" = a list item)
    key: str
    value_col: int            # column where the value text starts
    value: str                # raw value text (without the line ending)
    owner: int                # index of the nearest list-item line above (or -1)


def split_lines(text: str) -> List[str]:
    """Lines WITH their endings kept (only \\n is a line break); ''.join(...) == text."""
    parts = text.split("\n")
    out = [p + "\n" for p in parts[:-1]]
    if parts[-1]:
        out.append(parts[-1])
    return out


def _body(line: str) -> Tuple[str, str]:
    stripped = line.rstrip("\n")
    body = stripped.rstrip("\r")
    return body, line[len(body):]


def scan(lines: List[str]) -> List[Rec]:
    """Every `key: value` line with the path of containers above it."""
    stack: List[List] = []            # [indent, name, owner_line]
    recs: List[Rec] = []
    for idx, line in enumerate(lines):
        body, _eol = _body(line)
        if not body.strip() or body.lstrip().startswith("#"):
            continue
        m = _KEY_LINE.match(body)
        indent = len(body) - len(body.lstrip(" "))
        dash = _DASH_LINE.match(body)
        if dash:
            while stack and (stack[-1][0] > indent or (stack[-1][0] == indent and stack[-1][1] == "-")):
                stack.pop()
            stack.append([indent, "-", idx])
        else:
            while stack and stack[-1][0] >= indent:
                stack.pop()
        if not m:
            continue
        key_indent = len(m.group("indent")) + len(m.group("dash") or "")
        owner = -1
        for ent in reversed(stack):
            if ent[1] == "-":
                owner = ent[2]
                break
        path = tuple(e[1] for e in stack)
        recs.append(Rec(idx, path, m.group("key"), m.start("value"), m.group("value"), owner))
        stack.append([key_indent, m.group("key"), owner])
    return recs


def unquote(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return raw


def quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


# ---- reading -----------------------------------------------------------------------------------

def _serial_slot(rec: Rec) -> Optional[Tuple[str, Optional[str]]]:
    p = rec.path
    if rec.key != "serial" or not p or p[0] != "state":
        return None
    if len(p) == 5 and p[1:4] == ("inventory", "items", "backpack"):
        return "backpack", p[4]
    if len(p) == 6 and p[1:4] == ("inventory", "equipped_inventory", "equipped") and p[5] == "-":
        return "equipped", p[4]
    if p == ("state", "lostloot", "items", "-"):
        return "lostloot", None
    return None


def list_items(text: str) -> List[SaveItem]:
    lines = split_lines(text)
    items: List[SaveItem] = []
    n_lost = 0
    for rec in scan(lines):
        hit = _serial_slot(rec)
        if hit is None:
            continue
        area, slot = hit
        if area == "lostloot":
            slot = str(n_lost)
            n_lost += 1
        items.append(SaveItem("%s/%s" % (area, slot), area, slot, unquote(rec.value), rec.idx + 1))
    return items


def _under(recs: List[Rec], path: Tuple[str, ...]) -> Dict[str, Rec]:
    return {r.key: r for r in recs if r.path == path}


def _int(rec: Optional[Rec]) -> Optional[int]:
    if rec is None or not _INT.match(rec.value.strip()):
        return None
    return int(rec.value.strip())


def _character_xp(recs: List[Rec]) -> Dict[str, Rec]:
    """level/points recs of the experience entry whose `type` is `character`."""
    by_owner: Dict[int, Dict[str, Rec]] = {}
    for r in recs:
        if r.path == ("state", "experience", "-"):
            by_owner.setdefault(r.owner, {})[r.key] = r
    for entry in by_owner.values():
        t = entry.get("type")
        if t is not None and unquote(t.value) == "character":
            return entry
    return {}


def summary(text: str) -> Dict[str, object]:
    recs = scan(split_lines(text))
    state = _under(recs, ("state",))
    cur = _under(recs, ("state", "currencies"))
    xp = _character_xp(recs)
    return {
        "name": unquote(state["char_name"].value) if "char_name" in state else None,
        "class": unquote(state["class"].value) if "class" in state else None,
        "difficulty": unquote(state["player_difficulty"].value) if "player_difficulty" in state else None,
        "level": _int(xp.get("level")),
        "points": _int(xp.get("points")),
        "currencies": {k: _int(r) for k, r in cur.items()},
        "items": len(list_items(text)),
    }


# ---- patching ----------------------------------------------------------------------------------

def _replace_value(lines: List[str], rec: Rec, new_value: str) -> str:
    line = lines[rec.idx]
    body, eol = _body(line)
    lines[rec.idx] = body[:rec.value_col] + new_value + eol
    return "".join(lines)


def _int_arg(value: object, what: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SaveError("%s must be an integer, got %r" % (what, value))
    if not lo <= value <= hi:
        raise SaveError("%s must be from %d to %d, got %d" % (what, lo, hi, value))
    return value


def set_currency(text: str, name: str, value: int) -> str:
    value = _int_arg(value, "currency value", 0, MAX_CURRENCY)
    lines = split_lines(text)
    cur = _under(scan(lines), ("state", "currencies"))
    if name not in cur:
        raise SaveError("this save has no currency %r (it has: %s); refusing to insert a new line"
                        % (name, ", ".join(cur) or "none"))
    if _int(cur[name]) is None:
        raise SaveError("currency %r is not a plain integer on its line: %r" % (name, cur[name].value))
    return _replace_value(lines, cur[name], str(value))


_POOLS = ("domains", "local", "progression_shared", "point_pools")
_GRAPHS = ("domains", "local", "progression_shared", "graphs", "-")
_SPENT_GRAPH = "sdu_upgrades"
ECHO_POOL = "echotokenprogresspoints"


def _shared_pools(recs: List[Rec]) -> Dict[str, Rec]:
    return _under(recs, _POOLS)


def set_shared_point_pool(text: str, name: str, value: int) -> str:
    """Set one integer under domains > local > progression_shared > point_pools (profile saves).
    The character save's top-level `progression: point_pools` is deliberately NOT reachable from here."""
    value = _int_arg(value, "point pool value", 0, MAX_POINTS)
    lines = split_lines(text)
    pools = _shared_pools(scan(lines))
    if not pools:
        raise SaveError("this save has no domains > local > progression_shared > point_pools section "
                        "(is it a profile save?); refusing to insert one")
    if name not in pools:
        raise SaveError("this save has no shared point pool %r (it has: %s); refusing to insert a new line"
                        % (name, ", ".join(pools)))
    if _int(pools[name]) is None:
        raise SaveError("point pool %r is not a plain integer on its line: %r" % (name, pools[name].value))
    return _replace_value(lines, pools[name], str(value))


def shared_pool_report(text: str, name: str = ECHO_POOL) -> Optional[Dict[str, object]]:
    """Read-only: the pool's value, the points spent in graph sdu_upgrades, and available = value - spent.
    None when the save has no such shared pool (a character save, or a profile without it)."""
    recs = scan(split_lines(text))
    pools = _shared_pools(recs)
    if name not in pools or _int(pools[name]) is None:
        return None
    spent, graph = 0, None
    for r in recs:
        if r.path == _GRAPHS and r.key == "name":
            graph = unquote(r.value)
        elif graph == _SPENT_GRAPH and r.path == _GRAPHS + ("nodes", "-") and r.key == "points_spent":
            spent += _int(r) or 0
    value = _int(pools[name])
    return {"name": name, "value": value, "spent": spent, "available": value - spent,
            "pools": {k: _int(v) for k, v in pools.items()}}


def set_progress(text: str, level: Optional[int] = None, points: Optional[int] = None) -> str:
    if level is None and points is None:
        raise SaveError("nothing to set: give a level and/or points")
    lines = split_lines(text)
    xp = _character_xp(scan(lines))
    if not xp:
        raise SaveError("no experience entry of type 'character' in this save")
    edits: List[Tuple[Rec, str]] = []
    for key, val, lo, hi in (("level", level, LEVEL_MIN, LEVEL_MAX), ("points", points, 0, MAX_POINTS)):
        if val is None:
            continue
        _int_arg(val, key, lo, hi)
        if key not in xp or _int(xp[key]) is None:
            raise SaveError("the character experience entry has no integer %r line" % key)
        edits.append((xp[key], str(val)))
    for rec, new in edits:                    # values only, so line indexes never shift
        body, eol = _body(lines[rec.idx])
        lines[rec.idx] = body[:rec.value_col] + new + eol
    return "".join(lines)


def check_serial(serial: object) -> str:
    if not isinstance(serial, str) or not _SERIAL_OK.match(serial):
        raise SaveError("not a serial: it must start with '@U' and be printable ASCII without spaces")
    return serial


def set_serial(text: str, ref: str, serial: str) -> str:
    check_serial(serial)
    lines = split_lines(text)
    n_lost = 0
    for rec in scan(lines):
        hit = _serial_slot(rec)
        if hit is None:
            continue
        area, slot = hit
        if area == "lostloot":
            slot = str(n_lost)
            n_lost += 1
        if "%s/%s" % (area, slot) == ref:
            return _replace_value(lines, rec, quote(serial))
    known = [it.ref for it in list_items(text)]
    raise SaveError("no item %r in this save (%d items; e.g. %s)" % (ref, len(known), ", ".join(known[:3]) or "none"))


def changed_lines(before: str, after: str) -> List[Tuple[int, str, str]]:
    a, b = split_lines(before), split_lines(after)
    if len(a) == len(b):
        return [(i + 1, x.rstrip("\r\n"), y.rstrip("\r\n")) for i, (x, y) in enumerate(zip(a, b)) if x != y]
    out: List[Tuple[int, str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        span = max(i2 - i1, j2 - j1)
        for k in range(span):
            old = a[i1 + k].rstrip("\r\n") if i1 + k < i2 else ""
            new = b[j1 + k].rstrip("\r\n") if j1 + k < j2 else ""
            out.append((i1 + k + 1, old, new))
    return out
