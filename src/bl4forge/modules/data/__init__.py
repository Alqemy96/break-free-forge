"""data: Serve the game's manifest tables (categories, parts, rarity/pack meta, drops) as read-only lookups.

Everything is loaded lazily from `config.manifest_dir` and cached on the INSTANCE (no module-level
state), so two DataModules pointed at different data dirs never interfere. Lookups never raise when
data is missing: `available()` is False and they return empties; only `require()` raises DataMissing.
Everything handed out is read-only (see _frozen.py). See CONTRACT.md in this directory.


DISCLOSURE (what this code does)
  Reads: the extracted game-data manifest under <data_dir>/manifest/ (user-supplied; not shipped). Writes: nothing. Network: none. Risk: none; without it names, rarity and odds are unavailable and the module reports 'degraded'.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Dict, List, Mapping, NamedTuple, Optional, Tuple

from ...core.errors import DataMissing
from ...core.module import Module, ModuleContext
from ...core.ports import DataPort
from ...core.types import HealthCheck, HealthReport
from . import _names
from ._frozen import FrozenDict, FrozenList, freeze
from ._tsv import read_json, read_tsv, to_int

_EMPTY = FrozenDict()            # immutable shared "nothing here" answer
_PART_FILE = re.compile(r"^(.*)-(\d+)\.tsv$")     # parts/<slug>-<category_id>.tsv
_VERSION_FILE = "VERSION"        # optional marker file inside the manifest dir (see manifest_version)
_WEAPON_WORDS = ("pistol", "shotgun", "smg", "sniper", " ar", "assault", "heavy weapon", "weapon")


class _PartScan(NamedTuple):
    files: Mapping[int, Path]         # category_id -> parts table path
    tsv_on_disk: int                  # every *.tsv found in parts/
    duplicates: Tuple[int, ...]       # category ids claimed by more than one file
    unmatched: Tuple[str, ...]        # *.tsv files that do not look like <slug>-<id>.tsv


_NO_SCAN = _PartScan(_EMPTY, 0, (), ())


class DataModule(Module):
    name = "data"
    purpose = "Serve the game's manifest tables (categories, parts, rarity/pack meta, drops) as read-only lookups."
    requires = ()
    port = DataPort

    def __init__(self, ctx: ModuleContext):
        super().__init__(ctx)
        self._dir = Path(self.config.manifest_dir)
        self._lock = threading.RLock()
        self._avail = False
        self._cache: Dict[str, object] = {}
        self._tables: Dict[int, Mapping[int, str]] = {}
        self._problems: Dict[str, str] = {}     # file -> why it could not be read (for health)

    # ---- availability -------------------------------------------------------------------------
    def available(self) -> bool:
        """True when the manifest extract is present (its `parts/` directory exists)."""
        if self._avail:
            return True
        try:
            found = (self._dir / "parts").is_dir()
        except OSError:
            found = False
        if found:
            self._avail = True
        return found

    def require(self) -> None:
        if not self.available():
            raise DataMissing(
                "manifest data not found at %s - part names, rarity and drop odds are unavailable. "
                "Serial encode/decode still works." % self._dir)

    def manifest_version(self) -> str:
        """Extract date/version of the manifest, or 'unknown'.

        The manifest files themselves carry no extract date (drops.json's `"version": 1` is the
        file's schema version). An optional text file `VERSION` in the manifest dir is honoured
        (first non-blank, non-# line), so the date can be recorded next to the data.
        """
        return self._cached("version", self._build_version, "unknown")

    def is_synthetic(self) -> bool:
        """True when the manifest is the bundled fictional demo set (its VERSION line starts 'SYNTHETIC')."""
        return self.manifest_version().upper().startswith("SYNTHETIC")

    def known_answers(self) -> Mapping[str, object]:
        """Health-check known answers shipped WITH the synthetic dataset (`known_answers.json`).

        Empty for any other manifest: the real-data known answers live in the modules themselves. Not in
        DataPort; callers must treat it as optional (`getattr(data, "known_answers", None)`).
        """
        if not self.is_synthetic():
            return _EMPTY
        return self._cached("known_answers", self._build_known_answers, _EMPTY)

    # ---- lookups ------------------------------------------------------------------------------
    def category_names(self) -> Mapping[int, str]:
        """category_id -> human-readable category name."""
        return self._cached("category_names", self._build_category_names, _EMPTY)

    def part_table(self, category_id: int) -> Mapping[int, str]:
        """index -> raw part name for one category. Empty when the category is unknown."""
        try:
            return self._tables[category_id]
        except (KeyError, TypeError):
            pass
        try:
            path = self._part_scan().files.get(category_id)
        except TypeError:               # unhashable category id
            return _EMPTY
        if path is None:
            return _EMPTY
        with self._lock:
            table = self._tables.get(category_id)
            if table is None:
                try:
                    table = self._build_part_table(path)
                except Exception as ex:          # lookups never raise
                    self._problems["parts/" + Path(path).name] = "%s: %s" % (type(ex).__name__, ex)
                    table = _EMPTY
                self._tables[category_id] = table
            return table

    def item_names(self) -> Mapping[str, str]:
        """`np_hellwalker` -> `Hellwalker` (the game's display-name table; keys lower-cased)."""
        return self._cached("item_names", self._build_item_names, _EMPTY)

    def part_meta(self, category_id: int, index: int) -> Mapping[str, object]:
        """The explicit part_meta.json entry for one part ref (`name`, `rarity`, `pack`, `tags`,
        whichever the game tagged), or {}. Rarity/pack are NEVER inferred from the part name."""
        entry = self._all_part_meta().get("%s:%s" % (category_id, index))
        return entry if isinstance(entry, dict) and entry else _EMPTY

    def drops(self) -> Mapping[str, object]:
        """drops.json as shipped: {'version', 'drops': [...], 'probabilities': {...}}."""
        return self._cached("drops", self._build_drops, _EMPTY)

    def drops_by_item(self) -> Mapping[str, List[dict]]:
        """lower-cased item name -> list of drop records."""
        return self._cached("drops_by_item", self._build_drops_by_item, _EMPTY)

    def is_weapon_category(self, category_id: Optional[int]) -> bool:
        try:
            name = (self.category_names().get(category_id) or "").lower()
        except TypeError:
            return False
        if not name or name.startswith("ammo") or name.startswith("turret"):
            return False
        return any(w in (" " + name) for w in _WEAPON_WORDS)

    # ---- presentation (labels only; part_meta is the authority for rarity) ----------------------
    def prettify_part(self, raw: str) -> str:
        return _names.prettify_part(raw, self.item_names())

    def prettify_legendary(self, raw_suffix: str) -> str:
        return _names.prettify_legendary(raw_suffix, self.item_names())

    # ---- loading ------------------------------------------------------------------------------
    def _cached(self, key: str, build, empty):
        """Build once per instance. While the manifest is absent nothing is cached (so data that
        appears later is picked up); a file that is missing/corrupt inside a present manifest is
        recorded for health() and answered with `empty`."""
        if not self.available():
            return empty
        try:
            return self._cache[key]
        except KeyError:
            pass
        with self._lock:
            if key not in self._cache:
                try:
                    value = build()
                except Exception as ex:          # lookups never raise
                    self._problems[key] = "%s: %s" % (type(ex).__name__, ex)
                    value = empty
                self._cache[key] = value
            return self._cache[key]

    def _all_part_meta(self) -> Mapping[str, object]:
        return self._cached("part_meta", self._build_part_meta, _EMPTY)

    def _part_scan(self) -> _PartScan:
        return self._cached("part_scan", self._build_part_scan, _NO_SCAN)

    def _build_version(self) -> str:
        try:
            text = (self._dir / _VERSION_FILE).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "unknown"
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
        return "unknown"

    def _build_category_names(self) -> Mapping[int, str]:
        out: Dict[int, str] = {}
        for r in read_tsv(self._dir / "category_names.tsv")[1:]:
            cid = to_int(r[0]) if len(r) >= 2 else None
            if cid is not None:
                out[cid] = r[1]
        return FrozenDict(out)

    def _build_part_scan(self) -> _PartScan:
        files: Dict[int, Path] = {}
        dupes: List[int] = []
        unmatched: List[str] = []
        tsv = 0
        pdir = self._dir / "parts"
        for fn in sorted(p.name for p in pdir.iterdir()):
            if not fn.endswith(".tsv"):
                continue
            tsv += 1
            m = _PART_FILE.match(fn)
            if not m:
                unmatched.append(fn)
                continue
            cid = int(m.group(2))
            if cid in files:
                dupes.append(cid)
            files[cid] = pdir / fn          # same category twice: the later name wins (deterministic)
        return _PartScan(FrozenDict(files), tsv, tuple(sorted(set(dupes))), tuple(unmatched))

    @staticmethod
    def _build_part_table(path) -> Mapping[int, str]:
        table: Dict[int, str] = {}
        for r in read_tsv(path)[1:]:
            idx = to_int(r[0]) if len(r) >= 2 else None
            if idx is not None:
                table[idx] = r[1]
        return FrozenDict(table)

    def _build_item_names(self) -> Mapping[str, str]:
        out: Dict[str, str] = {}
        for r in read_tsv(self._dir / "item_names.tsv"):
            if len(r) >= 2:
                out[r[0].strip().lower()] = r[1].strip()
        return FrozenDict(out)

    def _build_part_meta(self) -> Mapping[str, object]:
        data = read_json(self._dir / "part_meta.json")
        if not isinstance(data, dict):
            raise ValueError("part_meta.json is not a JSON object")
        return freeze(data)

    def _build_known_answers(self) -> Mapping[str, object]:
        data = read_json(self._dir / "known_answers.json")
        if not isinstance(data, dict):
            raise ValueError("known_answers.json is not a JSON object")
        return freeze(data)

    def _build_drops(self) -> Mapping[str, object]:
        data = read_json(self._dir / "drops.json")
        if not isinstance(data, dict):
            raise ValueError("drops.json is not a JSON object")
        return freeze(data)

    def _build_drops_by_item(self) -> Mapping[str, List[dict]]:
        grouped: Dict[str, List[dict]] = {}
        records = self.drops().get("drops", [])
        if isinstance(records, list):
            for d in records:
                if not isinstance(d, dict):
                    continue
                key = str(d.get("item_name", "")).strip().lower()
                if key:
                    grouped.setdefault(key, []).append(d)
        return FrozenDict({k: FrozenList(v) for k, v in grouped.items()})

    # ---- health -------------------------------------------------------------------------------
    def health(self) -> HealthReport:
        try:
            return self._health()
        except Exception as ex:          # contract: never raises
            return HealthReport(ok=False, summary="health check crashed: %s: %s" % (type(ex).__name__, ex),
                                checks=(HealthCheck("health", False, "%s: %s" % (type(ex).__name__, ex)),))

    def _health(self) -> HealthReport:
        if not self.available():
            msg = "manifest data not found at %s/manifest (no parts/ directory)" % self.config.data_label
            return HealthReport.from_checks([HealthCheck("available", False, msg)], summary=msg)
        checks = [HealthCheck("available", True, "%s/manifest" % self.config.data_label)]
        names = self.category_names()
        checks.append(HealthCheck("category_names", bool(names), "%d categories" % len(names)))
        scan = self._part_scan()
        n = len(scan.files)
        notes = ""
        if scan.duplicates:
            notes += "; duplicate category ids %s" % list(scan.duplicates)
        if scan.unmatched:
            notes += "; unrecognised file names %s" % list(scan.unmatched)
        checks.append(HealthCheck(
            "part_tables", n > 0 and n == scan.tsv_on_disk and not scan.duplicates,
            "%d part tables for %d .tsv files on disk%s" % (n, scan.tsv_on_disk, notes)))
        meta = self._all_part_meta()
        checks.append(HealthCheck("part_meta", bool(meta), "%d entries" % len(meta)))
        items = self.item_names()
        checks.append(HealthCheck("item_names", bool(items), "%d names" % len(items)))
        records = self.drops().get("drops")
        n_drops = len(records) if isinstance(records, list) else 0
        checks.append(HealthCheck("drops", n_drops > 0, "%d drop records" % n_drops))
        checks.append(HealthCheck("files_readable", not self._problems,
                                  "; ".join("%s: %s" % kv for kv in sorted(self._problems.items())) or "all read"))
        summary = "%d categories, %d part tables, %d part_meta entries, manifest version %s" % (
            len(names), n, len(meta), self.manifest_version())
        return HealthReport.from_checks(checks, summary=summary)


MODULE = DataModule
