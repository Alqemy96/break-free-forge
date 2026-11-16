"""Tiny file readers shared by the loaders (pure functions; no state)."""
from __future__ import annotations

import json
import os
from typing import Any, List


def read_tsv(path: "os.PathLike[str] | str") -> List[List[str]]:
    """Rows of a tab-separated file, blank lines dropped (same rules as the legacy reader)."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").rstrip("\r").split("\t") for ln in f if ln.strip()]


def read_json(path: "os.PathLike[str] | str") -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def to_int(text: str):
    """int(text) when `text` is all digits, else None (never raises)."""
    if not text.isdigit():
        return None
    try:
        return int(text)
    except ValueError:      # str.isdigit() is True for things like superscripts; int() disagrees
        return None
