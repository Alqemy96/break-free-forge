"""The JSON API: one `Api` object per server, wrapping the single `Forge` built at startup.

Outer-layer rules (same as the cli): no domain logic here. Handlers validate the request shape,
translate it into port calls on the Forge's modules, and shape the answer exactly as docs/WEB_API.md
says. Modules are reached through `Api.use(name)`, which turns a failed/blocked module into a 503
that names it, so one sick module only takes down the endpoints that need it.

Thread safety: the server is a ThreadingHTTPServer and the modules are read-only after startup.
The only mutable state in the mesh is memoisation inside modules (`catalog`'s per-serial dicts,
`data`'s lazy tables, guarded by its own lock). Those memos are plain dict get/set of values that
are pure functions of the key, so a race can only repeat work, never corrupt a result; hence no
lock is needed here. `Api` itself holds no mutable state (`random.SystemRandom` is stateless)."""
from __future__ import annotations

import base64
import binascii
import dataclasses
import random
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .. import __version__
from ..core import vocab
from ..core.doctor import diagnose, ok as doctor_ok
from ..core.errors import ForgeError, ModuleUnavailable, SaveError, SerialError
from ..core.forge import Forge
from ..core.types import ItemInfo, Loadout, LoadoutRequest, SearchQuery
from ._errors import bad_request, module_unavailable

LEVEL_MIN, LEVEL_MAX = 1, 100
SEED_MAX = 2 ** 31 - 1
SEARCH_LIMIT_DEFAULT, SEARCH_LIMIT_MAX = 25, 200
BUILD_MAX_REQUESTS = 200
BUILD_MAX_COUNT = 200
TITLE_MAX = 200
DEFAULT_TITLE = "Borderlands 4 Loadout"
STRUCTURAL_NOTE = "passed structural checks only; in-game validity is not guaranteed"
STRUCTURAL_FAIL_NOTE = "did not pass structural checks (see problems); in-game validity is not guaranteed"
TRANSFORM_OPS = ("relevel", "set_element", "reseed", "swap")
CLASSMOD_TYPES = ("classmod", "class_mod", "com")

# Item types the UI offers. `id` is what /api/search accepts as `type` (the catalog resolves it).
TYPES: Tuple[Dict[str, str], ...] = (
    {"id": "pistol", "label": "Pistol", "group": "weapon"},
    {"id": "shotgun", "label": "Shotgun", "group": "weapon"},
    {"id": "smg", "label": "SMG", "group": "weapon"},
    {"id": "assault_rifle", "label": "Assault Rifle", "group": "weapon"},
    {"id": "sniper", "label": "Sniper", "group": "weapon"},
    {"id": "heavy", "label": "Heavy Weapon", "group": "weapon"},
    {"id": "shield", "label": "Shield", "group": "gear"},
    {"id": "classmod", "label": "Class Mod", "group": "gear"},
    {"id": "repkit", "label": "Repair Kit", "group": "gear"},
    {"id": "grenade", "label": "Grenade", "group": "gear"},
    {"id": "enhancement", "label": "Enhancement", "group": "gear"},
)

_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")
_INT_RE = re.compile(r"[+-]?\d{1,18}")


# ---- request field access ---------------------------------------------------------------------

class Fields:
    """Typed, validating access to a query string (all values arrive as text) or a JSON object."""

    def __init__(self, data: Mapping[str, Any], from_query: bool = False):
        self.data = data
        self.from_query = from_query

    def raw(self, key: str) -> Any:
        return self.data.get(key)

    def text(self, key: str, required: bool = False) -> Optional[str]:
        """A stripped string, or None when absent/blank (an error when `required`)."""
        value = self.data.get(key)
        if value is not None and not isinstance(value, str):
            raise bad_request("%r must be a string" % key)
        value = (value or "").strip()
        if not value:
            if required:
                raise bad_request("%r is required" % key)
            return None
        return value

    def integer(self, key: str, lo: int, hi: int, required: bool = False) -> Optional[int]:
        value = self.data.get(key)
        if value is None or (self.from_query and isinstance(value, str) and not value.strip()):
            if required:
                raise bad_request("%r is required" % key)
            return None
        if isinstance(value, bool):
            raise bad_request("%r must be an integer" % key)
        if isinstance(value, str):
            if not self.from_query or not _INT_RE.fullmatch(value.strip()):
                raise bad_request("%r must be an integer" % key)
            value = int(value.strip())
        if not isinstance(value, int):
            raise bad_request("%r must be an integer" % key)
        if not lo <= value <= hi:
            raise bad_request("%r must be from %d to %d, got %d" % (key, lo, hi, value))
        return value

    def boolean(self, key: str, default: bool) -> bool:
        value = self.data.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            low = value.strip().lower()
            if low in _TRUE:
                return True
            if low in _FALSE:
                return False
        raise bad_request("%r must be true or false (or 1/0)" % key)


def _check_element(element: Optional[str], where: str = "") -> Optional[str]:
    try:
        return vocab.normalize_element(element)
    except ValueError as ex:
        raise bad_request("%s%s" % (where, ex))


def _is_classmod_type(type_: Optional[str]) -> bool:
    return bool(type_) and type_.strip().lower().replace(" ", "_") in CLASSMOD_TYPES


# ---- the API ------------------------------------------------------------------------------------

class Api:
    def __init__(self, forge: Forge):
        self.forge = forge
        self._rng = random.SystemRandom()

    # ---- module access ----
    def use(self, name: str):
        """The module instance, or a 503 that names it. A DEGRADED module is still served."""
        try:
            return self.forge.module(name)
        except ModuleUnavailable as ex:
            raise module_unavailable(name, str(ex))
        except ForgeError as ex:                # e.g. the Forge was built with `only=` and lacks it
            raise module_unavailable(name, str(ex))

    def _try(self, fn: Callable[[], Any]) -> Any:
        """Best-effort lookup for display-only values: None when the module cannot answer."""
        try:
            return fn()
        except Exception:
            return None

    # ---- GET /api/meta, /api/health, /api/stats ----
    def meta(self, f: Fields) -> dict:
        """Never 503s: the UI loads this first, and a sick module should show up as nulls + /api/health."""
        cfg = self.forge.config
        owned = list(cfg.owned_packs)
        live = self._try(lambda: self.forge.module("rules").owned_packs())
        if live is not None:
            owned = [p for p in owned if p in live] + sorted(p for p in live if p not in owned)
        return {
            "version": __version__,
            "level": cfg.level,
            "character": cfg.character,
            "owned_packs": owned,
            "catalog_count": self._try(lambda: self.forge.module("catalog").count()),
            "manifest_version": self._try(lambda: self.forge.module("data").manifest_version()),
            "elements": [{"id": e, "label": vocab.ELEMENT_LABELS.get(e, e)} for e in vocab.ELEMENTS],
            "rarities": list(vocab.RARITIES),
            "characters": list(vocab.CHARACTERS),
            "types": [dict(t) for t in TYPES],
        }

    def health(self, f: Fields) -> dict:
        rows = diagnose(self.forge)
        return {"ok": doctor_ok(rows), "modules": rows}

    def stats(self, f: Fields) -> dict:
        stats = self.use("catalog").stats()
        return {name: dict(table) for name, table in stats.items()}

    # ---- GET /api/search ----
    def search(self, f: Fields) -> dict:
        query = f.text("query")
        type_ = f.text("type")
        element = f.text("element")
        manufacturer = f.text("manufacturer")
        rarity = f.text("rarity")
        character = f.text("character")
        limit = f.integer("limit", 1, SEARCH_LIMIT_MAX)
        level = f.integer("level", LEVEL_MIN, LEVEL_MAX)
        include_unowned = f.boolean("include_unowned", False)
        verify_element = f.boolean("verify_element", True)
        _check_element(element)
        notes: List[str] = []
        if not character and _is_classmod_type(type_):
            character = self.forge.config.character
            notes.append("no character given for a class-mod search; using %s (config)" % character)

        catalog = self.use("catalog")
        ops = self.use("ops")
        result = catalog.search(SearchQuery(
            query=query, type=type_, element=element, manufacturer=manufacturer, rarity=rarity,
            character=character, limit=limit or SEARCH_LIMIT_DEFAULT, verify_element=verify_element,
            include_unowned=include_unowned))
        rows = [self._search_row(ops, entry, level) for entry in result.entries]
        hidden = []
        if result.hidden_by_pack:
            rules = self._try(lambda: self.forge.module("rules"))
            for pack, count in sorted(result.hidden_by_pack.items()):
                label = self._try(lambda: rules.pack_label(pack)) if rules is not None else None
                hidden.append({"pack": pack, "label": label or pack, "count": count})
        return {
            "count": len(rows), "level": level, "results": rows, "hidden": hidden,
            "dropped_element_mismatch": result.dropped_element_mismatch, "notes": notes,
        }

    def _search_row(self, ops, entry, level: Optional[int]) -> dict:
        """One catalog entry as a result row. The catalog's labels are hints; `decoded` is the truth
        (ops.describe of the serial actually shown). A failed re-level is a warning, never silent."""
        serial = entry.serial
        warnings: List[str] = []
        relevel_failed = False
        if level is not None:
            try:
                serial = ops.relevel(entry.serial, level)
            except SerialError as ex:
                relevel_failed = True
                warnings.append("re-level to %d failed (%s) - code left at its stored level" % (level, ex))
        shown = None
        try:
            info = ops.describe(serial)
            shown = info.level
            warnings = list(info.warnings) + warnings
            if level is not None and not relevel_failed and shown is not None and shown != level:
                warnings.append("requested level %d but the code decodes as %d" % (level, shown))
            decoded = {"display_name": info.display_name, "category": info.category, "rarity": info.rarity,
                       "element": info.element, "owned": info.owned, "warnings": warnings}
        except SerialError as ex:
            warnings.append("decode failed: %s" % ex)
            decoded = {"display_name": None, "category": None, "rarity": None, "element": None,
                       "owned": None, "warnings": warnings}
        return {
            "serial": serial, "name": entry.name, "type": entry.type, "weapon_type": entry.weapon_type,
            "manufacturer": entry.manufacturer, "label": entry.label, "rarity": entry.rarity,
            "element": entry.element, "source": entry.source, "level": shown, "decoded": decoded,
        }

    # ---- POST /api/identify ----
    def identify(self, f: Fields) -> dict:
        serial = f.text("serial", required=True)
        level = f.integer("level", LEVEL_MIN, LEVEL_MAX)
        ops = self.use("ops")
        if level is not None:
            serial = ops.relevel(serial, level)
        return self._identify_payload(serial)

    def _is_weapon(self, info: ItemInfo) -> bool:
        return bool(self.use("data").is_weapon_category(info.category_id))

    def _identify_payload(self, serial: str) -> dict:
        ops = self.use("ops")
        rules = self.use("rules")
        info = ops.describe(serial)
        parts = ops.part_list(serial)
        is_weapon = self._is_weapon(info)
        return {
            "serial": serial,
            "info": info.to_dict(),
            "odds": ops.format_odds(ops.rarity_estimate(info)),
            "parts": [{"position": i, "token_index": p.token_index, "label": p.label(),
                       "category_id": p.category_id, "index": p.index, "raw": p.raw,
                       "category_link": p.category_link} for i, p in enumerate(parts)],
            "problems": list(rules.validate(serial)),
            "is_weapon": is_weapon,
            "can_set_element": is_weapon,
        }

    # ---- POST /api/transform ----
    def transform(self, f: Fields) -> dict:
        serial = f.text("serial", required=True)
        op = f.text("op", required=True)
        if op not in TRANSFORM_OPS:
            raise bad_request("unknown op %r (known: %s)" % (op[:40], ", ".join(TRANSFORM_OPS)))
        ops = self.use("ops")
        notes: List[str] = []
        extra: Dict[str, Any] = {}
        if op == "relevel":
            level = f.integer("level", LEVEL_MIN, LEVEL_MAX, required=True)
            new = ops.relevel(serial, level)
        elif op == "set_element":
            element = _check_element(f.text("element", required=True))
            info = ops.describe(serial)
            if not self._is_weapon(info):
                raise bad_request("set_element is for weapons: %s (%s) is gear and has no element"
                                  % (info.display_name or "this item", info.category or "unknown category"))
            new = ops.set_element(serial, element)
            if new == serial:
                notes.append("serial unchanged (already %s)" % element)
        elif op == "reseed":
            seed = f.integer("seed", 0, SEED_MAX)
            if seed is None:
                seed = self._rng.randint(0, SEED_MAX)
            old = ops.get_seed(serial)
            new = ops.set_seed(serial, seed)
            extra["seed"] = seed
            notes.append("seed %d (was %s)" % (seed, old if old is not None else "none"))
        else:  # swap
            source = f.text("source", required=True)
            positions = self._positions(f.raw("positions"))
            allow_cross = f.boolean("allow_cross", False)
            new = ops.swap_parts(serial, source, positions, allow_cross=allow_cross)

        payload = self._identify_payload(new)
        warnings = list(payload["info"]["warnings"])
        if op == "swap":
            problems = payload["problems"]
            warnings += problems
            warnings.append(STRUCTURAL_FAIL_NOTE if problems else STRUCTURAL_NOTE)
        payload["previous"] = serial
        payload.update(extra)
        payload["note"] = "; ".join(notes + warnings)
        return payload

    @staticmethod
    def _positions(raw: Any) -> List[int]:
        if not isinstance(raw, list) or not raw:
            raise bad_request("'positions' must be a non-empty array of part positions from /api/identify")
        for p in raw:
            if isinstance(p, bool) or not isinstance(p, int) or p < 0:
                raise bad_request("'positions' must contain only non-negative integers")
        return list(raw)

    # ---- POST /api/diff ----
    def diff(self, f: Fields) -> dict:
        a = f.text("a", required=True)
        b = f.text("b", required=True)
        return {"rows": [dict(r) for r in self.use("ops").diff(a, b)]}

    # ---- POST /api/build ----
    def build(self, f: Fields) -> dict:
        raw = f.raw("requests")
        level = f.integer("level", LEVEL_MIN, LEVEL_MAX)
        title = f.text("title") or DEFAULT_TITLE
        if len(title) > TITLE_MAX:
            raise bad_request("'title' is too long (max %d characters)" % TITLE_MAX)
        notes: List[str] = []
        requests = self._parse_requests(raw, notes)
        builder = self.use("builder")
        render = self.use("render")
        loadout = builder.build(requests, level=level, title=title)
        if notes:   # server-side notices belong on the sheet too, so they go through the Loadout
            loadout = dataclasses.replace(loadout, warnings=tuple(loadout.warnings) + tuple(notes))
        return {"loadout": self._loadout_dict(loadout), "html": render.html(loadout), "text": render.text(loadout)}

    _STR_FIELDS = ("group", "serial", "query", "type", "element", "manufacturer", "rarity", "character",
                   "note", "display_name", "label", "name", "label_name")
    _SEARCH_FIELDS = ("query", "type", "element", "manufacturer", "rarity", "character")
    _KNOWN_KEYS = set(LoadoutRequest.__dataclass_fields__) | {"label_name"}

    def _parse_requests(self, raw: Any, notes: List[str]) -> List[LoadoutRequest]:
        if not isinstance(raw, list) or not raw:
            raise bad_request("'requests' must be a non-empty array of loadout requests")
        if len(raw) > BUILD_MAX_REQUESTS:
            raise bad_request("too many requests (max %d)" % BUILD_MAX_REQUESTS)
        character = self.forge.config.character
        out: List[LoadoutRequest] = []
        for i, item in enumerate(raw):
            where = "requests[%d]: " % i
            if not isinstance(item, dict):
                raise bad_request(where + "must be a JSON object")
            for key in self._STR_FIELDS:
                if item.get(key) is not None and not isinstance(item[key], str):
                    raise bad_request(where + "%r must be a string" % key)
            count = item.get("count")
            if count is not None and (isinstance(count, bool) or not isinstance(count, int)
                                      or not 1 <= count <= BUILD_MAX_COUNT):
                raise bad_request(where + "'count' must be an integer from 1 to %d" % BUILD_MAX_COUNT)
            unknown = sorted(str(k) for k in item if k not in self._KNOWN_KEYS)
            if unknown:
                notes.append(where + "ignoring unknown key(s): %s" % ", ".join(unknown))
            try:
                req = LoadoutRequest.from_dict(item)
            except (TypeError, ValueError) as ex:
                raise bad_request(where + "invalid (%s)" % ex)
            if req.serial:
                req = dataclasses.replace(req, serial=req.serial.strip())
            if not req.serial:
                if not any((getattr(req, name) or "").strip() for name in self._SEARCH_FIELDS):
                    raise bad_request(where + "needs a 'serial' or at least one search field (%s)"
                                      % ", ".join(self._SEARCH_FIELDS))
                _check_element(req.element, where)
                if not (req.character or "").strip() and _is_classmod_type(req.type):
                    notes.append(where + "class mod search without a character; using %s (config)" % character)
                    req = dataclasses.replace(req, character=character)
            out.append(req)
        return out

    # ---- save files (POST /api/save/*): stateless, bytes/text in and out, no file paths ----
    def _save_platform(self, f: Fields) -> Tuple[str, Optional[str]]:
        platform = (f.text("platform") or "ps5").lower()
        if platform not in ("ps5", "pc"):
            raise bad_request("'platform' must be ps5 or pc")
        steam_id = f.text("steam_id")
        if platform == "pc" and not steam_id:
            raise bad_request("'steam_id' is required for a pc save")
        return platform, steam_id

    def _save_items(self, yaml_text: str) -> List[dict]:
        save, ops = self.use("save"), self.use("ops")
        rows = []
        for it in save.list_items(yaml_text):
            row = dict(it.to_dict(), name=None, level=None, rarity=None, category=None, element=None,
                       warnings=[], error=None)
            try:
                info = ops.describe(it.serial)
                row.update(name=info.display_name, level=info.level, rarity=info.rarity,
                           category=info.category, element=info.element, warnings=list(info.warnings))
            except SerialError as ex:
                row["error"] = str(ex)
            rows.append(row)
        return rows

    def save_open(self, f: Fields) -> dict:
        """{data_b64, platform?, steam_id?} -> the YAML text, a summary, and every item with its decoded name."""
        platform, steam_id = self._save_platform(f)
        try:
            raw = base64.b64decode(f.text("data_b64", required=True), validate=True)
        except (binascii.Error, ValueError):
            raise bad_request("'data_b64' is not valid base64")
        save = self.use("save")
        yaml_text = save.decrypt_pc(raw, steam_id) if platform == "pc" else save.decrypt_ps5(raw)
        return {"sha256": save.sha256(raw), "platform": platform, "yaml": yaml_text,
                "summary": save.summary(yaml_text), "items": self._save_items(yaml_text)}

    def save_items(self, f: Fields) -> dict:
        yaml_text = self._yaml_field(f)
        return {"summary": self.use("save").summary(yaml_text), "items": self._save_items(yaml_text)}

    @staticmethod
    def _yaml_field(f: Fields) -> str:
        value = f.raw("yaml")
        if not isinstance(value, str) or not value.strip():
            raise bad_request("'yaml' is required (the text from /api/save/open)")
        return value

    def save_apply(self, f: Fields) -> dict:
        """{yaml, edits:[{op:'currency',name,value} | {op:'level',level?,points?} | {op:'serial',ref,serial}]}
        -> the patched YAML and the exact lines that changed. Edits apply in order, each one line."""
        yaml_text = self._yaml_field(f)
        edits = f.raw("edits")
        if not isinstance(edits, list) or not edits or len(edits) > 100:
            raise bad_request("'edits' must be a non-empty array (at most 100)")
        save = self.use("save")
        ops = None
        current = yaml_text
        for n, e in enumerate(edits):
            if not isinstance(e, dict):
                raise bad_request("edits[%d] must be an object" % n)
            op = e.get("op")
            if op == "currency":
                if not isinstance(e.get("name"), str):
                    raise bad_request("edits[%d]: 'name' is required" % n)
                current = save.set_currency(current, e["name"], e.get("value"))
            elif op == "point_pool":
                if not isinstance(e.get("name"), str):
                    raise bad_request("edits[%d]: 'name' is required" % n)
                current = save.set_shared_point_pool(current, e["name"], e.get("value"))
            elif op == "level":
                current = save.set_progress(current, level=e.get("level"), points=e.get("points"))
            elif op == "serial":
                ops = ops or self.use("ops")
                if not isinstance(e.get("serial"), str):
                    raise bad_request("edits[%d]: 'serial' is required" % n)
                ops.describe(e["serial"].strip())               # SerialError -> 400: never write junk
                current = save.set_serial(current, str(e.get("ref")), e["serial"].strip())
            else:
                raise bad_request("edits[%d]: unknown op %r (known: currency, point_pool, level, serial)" % (n, str(op)[:40]))
        changed = [{"line": n, "old": old, "new": new} for n, old, new in save.changed_lines(yaml_text, current)]
        return {"yaml": current, "changed_lines": changed, "summary": save.summary(current)}

    def save_write(self, f: Fields) -> dict:
        """{yaml, platform?, steam_id?} -> the re-wrapped save as base64, proven to decrypt back to the
        same YAML. The server never writes a file: the caller saves the bytes as a COPY."""
        yaml_text = self._yaml_field(f)
        platform, steam_id = self._save_platform(f)
        save = self.use("save")
        blob = save.encrypt_pc(yaml_text, steam_id) if platform == "pc" else save.encrypt_ps5(yaml_text)
        back = save.decrypt_pc(blob, steam_id) if platform == "pc" else save.decrypt_ps5(blob)
        if back != yaml_text:
            raise SaveError("internal check failed: the re-wrapped save does not decrypt to the given YAML")
        return {"data_b64": base64.b64encode(blob).decode("ascii"), "bytes": len(blob),
                "sha256": save.sha256(blob), "platform": platform, "verified": True}

    @staticmethod
    def _loadout_dict(loadout: Loadout) -> dict:
        items = []
        for item in loadout.items:
            d = dataclasses.asdict(item)
            d["shown_name"] = item.shown_name
            items.append(d)
        return {"title": loadout.title, "level": loadout.level, "groups": list(loadout.groups),
                "unmatched": list(loadout.unmatched), "warnings": list(loadout.warnings), "items": items}


# ---- route table --------------------------------------------------------------------------------

Handler = Callable[[Api, Fields], dict]

#: path -> (method, handler). HEAD is served wherever GET is.
ROUTES: Dict[str, Tuple[str, Handler]] = {
    "/api/meta": ("GET", Api.meta),
    "/api/health": ("GET", Api.health),
    "/api/stats": ("GET", Api.stats),
    "/api/search": ("GET", Api.search),
    "/api/identify": ("POST", Api.identify),
    "/api/transform": ("POST", Api.transform),
    "/api/diff": ("POST", Api.diff),
    "/api/build": ("POST", Api.build),
    "/api/save/open": ("POST", Api.save_open),
    "/api/save/items": ("POST", Api.save_items),
    "/api/save/apply": ("POST", Api.save_apply),
    "/api/save/write": ("POST", Api.save_write),
}
