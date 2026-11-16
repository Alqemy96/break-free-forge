"""Loading and cleaning the community serial database (private to the catalog module).

The file is a JSON list of loosely typed rows (scraped text). Everything here is defensive: a row
that cannot be understood is skipped and COUNTED in the load report, never allowed to raise out of
a search. Nothing in this file is module-level mutable state; `load_database` returns fresh values.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, NamedTuple, Optional, Tuple

from ...core import vocab
from ...core.errors import DataMissing
from ...core.types import CatalogEntry

# Database labels that mean "this item has no element". NOT 'none': in vocab that is an alias of
# 'impact'. The shipped database writes 'N/A'.
_NO_ELEMENT = frozenset(("", "n/a", "na", "-", "—"))


class Row(NamedTuple):
    """One database row: the public entry plus the lower-cased fields the filters compare against."""
    entry: CatalogEntry
    name_l: str
    kind: str            # (weaponType + ' ' + type), lower-cased, spaces -> '_' (legacy `cand`)
    manufacturer_l: str
    rarity_l: str
    source_l: str


class Loaded(NamedTuple):
    rows: Tuple[Row, ...]
    by_serial: Dict[str, CatalogEntry]      # first row wins for a duplicated serial
    report: Dict[str, int]


def clean_serial(part_string: Any) -> Optional[str]:
    """The '@U...' serial inside a raw `partString` (which carries quotes and a trailing comma).

    Same algorithm as legacy `_clean_serial`: from the first '@U' up to a quote, backslash or space.
    """
    if not isinstance(part_string, str):
        return None
    start = part_string.find("@U")
    if start < 0:
        return None
    out = []
    for ch in part_string[start:]:
        if ch == '"' or ch == "\\" or ch.isspace():
            break
        out.append(ch)
    return "".join(out)


def element_from_label(raw: Any) -> Tuple[Optional[str], bool]:
    """Database `bulletType` -> (vocab element or None, recognised).

    'electric' becomes 'shock'; 'N/A' (and blank) is None; an unrecognised label is None with
    recognised=False so the loader can count it instead of guessing.
    """
    if raw is None:
        return None, True
    text = str(raw).strip().lower()
    if text in _NO_ELEMENT:
        return None, True
    try:
        return vocab.normalize_element(text), True
    except ValueError:
        return None, False


def _text(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def load_database(path: Path) -> Loaded:
    """Read and clean the database. Raises DataMissing if the file is absent or unreadable."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except OSError as ex:
        raise DataMissing("serial database not found or unreadable at %s (%s)" % (path, ex)) from ex
    except ValueError as ex:      # JSONDecodeError and UnicodeDecodeError are both ValueErrors
        raise DataMissing("serial database at %s is not valid JSON (%s)" % (path, ex)) from ex
    if not isinstance(raw, list):
        raise DataMissing("serial database at %s must be a JSON list of rows, got %s"
                          % (path, type(raw).__name__))

    report = {"rows_in_file": len(raw), "rows_loaded": 0, "skipped_not_an_object": 0,
              "skipped_no_serial": 0, "unrecognised_element_label": 0}
    rows = []
    by_serial: Dict[str, CatalogEntry] = {}
    for d in raw:
        if not isinstance(d, dict):
            report["skipped_not_an_object"] += 1
            continue
        serial = clean_serial(d.get("partString"))
        if not serial:
            report["skipped_no_serial"] += 1
            continue
        element, known = element_from_label(d.get("bulletType"))
        if not known:
            report["unrecognised_element_label"] += 1
        wtype, etype = _text(d.get("weaponType")), _text(d.get("type"))
        manufacturer = _text(d.get("manufacturer"))
        entry = CatalogEntry(
            serial=serial,
            name=_text(d.get("itemName"), "?"),
            type=etype,
            weapon_type=wtype,
            manufacturer=manufacturer,
            # legacy enrich(): the 'Jakobs Pistol' style label, else the broad type
            label=_text(d.get("manufacturerWeaponType")) or etype,
            rarity=_text(d.get("rarity")),
            element=element,
            source=_text(d.get("source")),
        )
        rows.append(Row(
            entry=entry,
            name_l=entry.name.lower(),
            kind=(wtype + " " + etype).lower().replace(" ", "_"),
            manufacturer_l=manufacturer.lower(),
            rarity_l=entry.rarity.lower(),
            source_l=entry.source.lower(),
        ))
        by_serial.setdefault(serial, entry)
    report["rows_loaded"] = len(rows)
    return Loaded(tuple(rows), by_serial, report)
