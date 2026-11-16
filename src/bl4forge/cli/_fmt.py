"""Text formatting helpers for the command line (presentation only).

DISCLOSURE (what this code does)
  Reads: nothing. Writes: nothing (returns strings). Network: none. Risk: none.
"""
from __future__ import annotations

from typing import Iterable, List, Mapping, Optional, Tuple

from ..core.vocab import ELEMENT_LABELS


def element_label(element: Optional[str]) -> str:
    """vocab name -> display label; '-' when there is none (gear, or unknown)."""
    if not element:
        return "-"
    return ELEMENT_LABELS.get(element, str(element))


def hidden_lines(hidden: Iterable[Tuple[str, str, int]]) -> List[str]:
    """(pack id, pack label, count) -> 'N hidden: needs <label> ...' lines."""
    return ["%d hidden: needs %s (pass --include-unowned to show them)" % (n, label)
            for _pack, label, n in hidden]


def table(title: str, rows: Mapping[str, int], width: int) -> List[str]:
    """A titled two-column table; `width` is a minimum, wider keys widen the column."""
    width = max([width] + [len(str(k)) + 1 for k in rows])
    lines = ["", "%s:" % title]
    for key, count in rows.items():
        lines.append("  %-*s %d" % (width, key, count))
    return lines
