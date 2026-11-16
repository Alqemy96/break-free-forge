"""catalog: Search the community serial database, verified against the decoded bitstream and ownership.

Ports the legacy `forge.load_db / _matches / _element_ok / _ownership_ok / search / cmd_catalog`.
Rows become `CatalogEntry`; the database element 'electric' is the vocab element 'shock'. Labels in
the database are HINTS: with `verify_element` every candidate is re-checked against the decoded
serial (through `ops.describe`) and mismatches are dropped and counted. Unowned items (judged by
`rules.serial_ownership`) are filtered unless `include_unowned`, and the filter is reported in
`SearchResult.hidden_by_pack`. See CONTRACT.md in this directory.


DISCLOSURE (what this code does)
  Reads: the serial database JSON at <data_dir>/bl4-serial-matches.json (user-supplied; not shipped). Writes: nothing. Network: none. Risk: none; without the file the module reports 'degraded' and commands that need it say so.
"""
from __future__ import annotations

import threading
from collections import Counter
from typing import Dict, Mapping, Optional, Tuple

from ...core import vocab
from ...core.errors import DataMissing
from ...core.module import Module, ModuleContext
from ...core.ports import CatalogPort
from ...core.types import CatalogEntry, HealthCheck, HealthReport, SearchQuery, SearchResult
from ._db import Loaded, clean_serial, load_database
from ._match import compile_query

# Known answers for health(): the first 'anarchy' shotgun row of the shipped database.
_KNOWN_SERIAL = r"@Uge(J0Fme!K{9I5@RG/*Fs6^dF^+SzB{X<<U4k{EX7U~sh7HS*<"
_HEALTH_ALIASES = ("ar", "assault_rifle", "repkit", "repair_kit", "grenade", "gadget", "sg", "ps")

DEFAULT_LIMIT = 25
UNKNOWN_PACK = "unknown"      # hidden_by_pack key when rules says 'not owned' without naming a pack


def _loose_element(value) -> Optional[str]:
    """An element as ops reported it, as a vocab name (None when absent or unrecognisable)."""
    if value is None:
        return None
    try:
        return vocab.normalize_element(str(value))
    except ValueError:
        return None


class CatalogModule(Module):
    name = "catalog"
    purpose = "Search the community serial database, verified against the decoded bitstream and ownership."
    requires = ('codec', 'data', 'rules', 'ops')
    port = CatalogPort

    def __init__(self, ctx: ModuleContext):
        super().__init__(ctx)
        self._lock = threading.Lock()
        self._db: Optional[Loaded] = None
        self._stats: Optional[Dict[str, Dict[str, int]]] = None
        # Per-instance memo of what the neighbours said about a serial. Neighbours are pure
        # functions of (serial, config), so this only saves repeated decoding across searches.
        self._decoded_element: Dict[str, Optional[str]] = {}
        self._ownership: Dict[str, Tuple[bool, Optional[str]]] = {}
        self._neighbour_errors = {"element_checks": 0, "ownership_checks": 0}

    # ---- loading --------------------------------------------------------------------------

    def _load(self) -> Loaded:
        """Lazy, cached per instance. While the file is absent nothing is cached (it may appear)."""
        db = self._db
        if db is not None:
            return db
        with self._lock:
            if self._db is None:
                self._db = load_database(self.config.serial_db_path)
            return self._db

    def diagnostics(self) -> Dict[str, int]:
        """Counters for what was skipped or tolerated, so nothing is lost silently (not in the port).

        Load report: rows_in_file, rows_loaded, skipped_not_an_object, skipped_no_serial,
        unrecognised_element_label. Search-time (distinct serials, cumulative per instance):
        element_check_errors / ownership_check_errors = a neighbour raised for that serial and the
        row was ALLOWED through (legacy behaviour: the decoder is at fault, not the player).
        """
        try:
            out = dict(self._load().report)
        except DataMissing:
            out = {}
        out["element_check_errors"] = self._neighbour_errors["element_checks"]
        out["ownership_check_errors"] = self._neighbour_errors["ownership_checks"]
        return out

    # ---- CatalogPort ----------------------------------------------------------------------

    def count(self) -> int:
        """Database ROWS (9,875), duplicates included. `search` de-duplicates serials."""
        return len(self._load().rows)

    def search(self, query: SearchQuery) -> SearchResult:
        if not isinstance(query, SearchQuery):
            raise TypeError("catalog.search() takes a SearchQuery, got %s" % type(query).__name__)
        db = self._load()
        limit = self._limit(query.limit)
        flt = compile_query(query)
        if flt is None or (limit is not None and limit <= 0):
            return SearchResult()
        verify = bool(flt.element is not None and query.verify_element and self._can_verify())
        entries = []
        hidden: Dict[str, int] = {}
        dropped = 0
        seen = set()
        for row in db.rows:
            if not flt.matches(row):
                continue
            serial = row.entry.serial
            # Same order as legacy: element check, then de-duplication, then ownership. A row the
            # bitstream contradicts is dropped (and counted) even if its serial repeats.
            if verify and not self._element_ok(serial, flt.element):
                dropped += 1
                continue
            if serial in seen:
                continue
            seen.add(serial)
            if not query.include_unowned:
                owned, pack = self._owned(serial)
                if not owned:
                    key = pack or UNKNOWN_PACK
                    hidden[key] = hidden.get(key, 0) + 1
                    continue
            entries.append(row.entry)
            if limit is not None and len(entries) >= limit:
                break
        return SearchResult(entries=tuple(entries), hidden_by_pack=dict(sorted(hidden.items())),
                            dropped_element_mismatch=dropped)

    def stats(self) -> Mapping[str, Mapping[str, int]]:
        """Counts over database ROWS. The port's three tables plus the ones legacy `catalog` printed.

        by_type, by_weapon_type, by_rarity, by_manufacturer, by_element (vocab names, 'N/A' = no
        element), by_character (class mods only). Each table is ordered most common first, like
        legacy `Counter.most_common()`. Returns fresh dicts: callers may mutate them.
        """
        stats = self._stats
        if stats is None:
            entries = [r.entry for r in self._load().rows]
            classmods = [e for e in entries if e.type == "classmod"]
            stats = {
                "by_type": _table(e.type or "?" for e in entries),
                "by_weapon_type": _table(e.weapon_type for e in entries if e.weapon_type),
                "by_rarity": _table(e.rarity or "?" for e in entries),
                "by_manufacturer": _table(e.manufacturer or "?" for e in entries),
                "by_element": _table(e.element or "N/A" for e in entries),
                "by_character": _table(
                    e.source.replace("GunCodes_classmod_", "").replace(".txt", "") for e in classmods),
            }
            self._stats = stats
        return {name: dict(table) for name, table in stats.items()}

    def find_by_serial(self, serial: str) -> Optional[CatalogEntry]:
        """The first database row for this serial (pasted quotes/commas are tolerated), or None."""
        cleaned = clean_serial(serial)
        if not cleaned:
            return None
        return self._load().by_serial.get(cleaned)

    # ---- verification (neighbours are consulted ONLY through their ports) ----------------

    @staticmethod
    def _limit(limit) -> Optional[int]:
        if limit is None:
            return None                      # no cap
        try:
            return int(limit)
        except (TypeError, ValueError):
            return DEFAULT_LIMIT

    def _can_verify(self) -> bool:
        """Legacy rule: without the manifest nobody can read an element, so do not drop anything."""
        try:
            return bool(self.dep("data").available())
        except Exception:
            return False

    def _element_ok(self, serial: str, wanted: str) -> bool:
        """True when the decoded serial carries `wanted`, or when it cannot say (gear, error)."""
        actual = self._decoded_element.get(serial, _MISSING)
        if actual is _MISSING:
            try:
                info = self.dep("ops").describe(serial)
                # manifest_ok False => the element is not trustworthy => cannot tell
                actual = _loose_element(info.element) if getattr(info, "manifest_ok", True) else None
            except Exception:
                # A malformed row (or a sick neighbour) must not crash a search. Like legacy the
                # row is ALLOWED, but the failure is counted (see diagnostics()).
                self._neighbour_errors["element_checks"] += 1
                actual = None
            self._decoded_element[serial] = actual
        return actual is None or actual == wanted      # None: gear has no element; trust the label

    def _owned(self, serial: str) -> Tuple[bool, Optional[str]]:
        cached = self._ownership.get(serial)
        if cached is None:
            try:
                owned, pack = self.dep("rules").serial_ownership(serial)
                cached = (bool(owned), pack if pack else None)
            except Exception:
                self._neighbour_errors["ownership_checks"] += 1
                cached = (True, None)        # legacy: a row that will not decode is allowed
            self._ownership[serial] = cached
        return cached

    # ---- health ---------------------------------------------------------------------------

    def health(self) -> HealthReport:
        """Known-answer checks; never raises. Order matters: the database first, then neighbours."""
        checks = []

        def check(name: str, fn) -> bool:
            try:
                ok, detail = fn()
            except Exception as ex:
                ok, detail = False, "%s: %s" % (type(ex).__name__, ex)
            checks.append(HealthCheck(name, bool(ok), detail))
            return bool(ok)

        def database():
            n = self.count()
            return n > 0, "%d rows, %d distinct serials" % (n, len(self._load().by_serial))

        def known_query():
            res = self.search(SearchQuery(query="anarchy", type="shotgun", limit=25,
                                          verify_element=False, include_unowned=True))
            serials = [e.serial for e in res.entries]
            ok = _KNOWN_SERIAL in serials and all("anarchy" in e.name.lower() for e in res.entries)
            return ok, "'anarchy' shotgun -> %d rows, known serial %s" % (
                len(serials), "present" if _KNOWN_SERIAL in serials else "MISSING")

        def aliases():
            empty = [a for a in _HEALTH_ALIASES if not self.search(SearchQuery(
                type=a, limit=1, verify_element=False, include_unowned=True)).entries]
            if empty:
                return False, "no rows for: " + ", ".join(empty)
            return True, "all %d aliases return rows" % len(_HEALTH_ALIASES)

        def find():
            entry = self.find_by_serial('"%s",' % _KNOWN_SERIAL)
            return entry is not None and entry.serial == _KNOWN_SERIAL, "known serial found by serial"

        def decodes():
            codec = self.dep("codec")
            rows = self._load().rows
            sample = [rows[0], rows[len(rows) // 2], rows[-1]]
            for r in sample:
                codec.decode(r.entry.serial)
            return True, "%d sample rows decode" % len(sample)

        def neighbours():
            ops, rules = self.dep("ops"), self.dep("rules")
            info = ops.describe(_KNOWN_SERIAL)
            owned, pack = rules.serial_ownership(_KNOWN_SERIAL)
            ok = info.element == "impact" and owned is True and pack is None
            return ok, "ops.describe -> element %r; rules.serial_ownership -> %r" % (info.element, (owned, pack))

        if check("database_loads", database):
            check("known_query", known_query)
            check("type_aliases", aliases)
            check("find_by_serial", find)
            check("sample_rows_decode", decodes)
            check("neighbours_verify", neighbours)
        bad = [c.name for c in checks if not c.ok]
        return HealthReport.from_checks(checks, "ok" if not bad else "failing: " + ", ".join(bad))


_MISSING = object()


def _table(values) -> Dict[str, int]:
    return dict(Counter(values).most_common())


MODULE = CatalogModule
