"""The commands. Each takes a Context and the parsed args and returns an exit code. They reach
modules only through `ctx.use(...)` (the Forge) and hold no domain logic: they translate arguments
into port calls and results into text/JSON, and they REPORT everything the modules report
(hidden-by-pack, dropped element labels, unmatched requests, warnings) instead of hiding it.

DISCLOSURE (what this code does)
  Reads: the serial database and manifest under data_dir (user-supplied), config.toml, and a --spec file for `build`. Writes: `build` writes the HTML and plain-text sheets named by --out/--plain and OVERWRITES them if they already exist. Network: none, except `serve`, which listens on 127.0.0.1 (a non-loopback --host is refused unless --allow-remote is given; that flag is risky, the UI has no login). `serve --open` launches the default browser on the local URL. Risk: output files are overwritten without asking; nothing is sent anywhere.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core import vocab
from ..core.doctor import diagnose, format_report, ok as doctor_ok
from ..core.errors import ForgeError, SerialError
from ..core.types import Loadout, LoadoutRequest, SearchQuery
from ._core import (CliError, Context, DOCTOR_HINT, EXIT_CHECK_FAILED, EXIT_NOTHING, EXIT_OK,
                    EXIT_UNAVAILABLE, EXIT_USAGE, emit_json, err, note, out, warn)
from ._fmt import element_label, hidden_lines, table

CLASSMOD_TYPES = ("classmod", "class_mod", "com")


def _serial(text: str) -> str:
    return text.strip()


def _effective_level(ctx: Context, args: Any) -> Optional[int]:
    """--no-relevel -> None; else --level; else the configured level."""
    if getattr(args, "no_relevel", False):
        return None
    return args.level if args.level is not None else ctx.config.level


def _is_classmod_type(type_: Optional[str]) -> bool:
    return bool(type_) and type_.strip().lower().replace(" ", "_") in CLASSMOD_TYPES


def _check_element(element: Optional[str], where: str = "") -> None:
    try:
        vocab.normalize_element(element)
    except ValueError as ex:
        raise CliError("%s%s" % (where, ex), EXIT_USAGE)


# ---- catalog -----------------------------------------------------------------------------------

_CATALOG_SECTIONS = (
    ("by_type", "By type", 14),
    ("by_weapon_type", "By weapon type", 16),
    ("by_rarity", "By rarity", 12),
    ("by_manufacturer", "By manufacturer", 12),
    ("by_element", "By element (database label; N/A = none)", 10),
    ("by_character", "Class-mod characters (from source)", 14),
)


def cmd_catalog(ctx: Context, args: Any) -> int:
    catalog = ctx.use("catalog")
    total = catalog.count()
    stats = catalog.stats()
    if args.json:
        emit_json(dict({"total": total}, **{k: dict(v) for k, v in stats.items()}))
        return EXIT_OK
    out("Total codes: %d" % total)
    for key, title, width in _CATALOG_SECTIONS:
        if stats.get(key):
            for line in table(title, stats[key], width):
                out(line)
    return EXIT_OK


# ---- search ------------------------------------------------------------------------------------

def _relevel_entry(codec, entry, level: Optional[int]) -> Dict[str, Any]:
    """The entry as a result row: serial re-leveled (a failure is a warning, never silent) and the
    level read back from the serial that is actually shown."""
    serial = entry.serial
    warnings: List[str] = []
    relevel_failed = False
    if level is not None:
        try:
            serial = codec.relevel(entry.serial, level)
        except SerialError as ex:
            relevel_failed = True
            warnings.append("re-level to %d failed (%s) - code left at its stored level" % (level, ex))
    try:
        shown = codec.get_level(codec.decode(serial))
    except SerialError as ex:
        shown = None
        warnings.append("decode failed: %s" % ex)
    if level is not None and not relevel_failed and shown is not None and shown != level:
        warnings.append("requested level %d but the code decodes as %d" % (level, shown))
    return {
        "name": entry.name, "manufacturer": entry.manufacturer, "label": entry.label,
        "type": entry.type, "weapon_type": entry.weapon_type, "rarity": entry.rarity,
        "element": entry.element, "source": entry.source, "level": shown, "serial": serial,
        "warnings": warnings,
    }


def cmd_search(ctx: Context, args: Any) -> int:
    catalog = ctx.use("catalog")
    codec = ctx.use("codec")
    _check_element(args.element)
    level = _effective_level(ctx, args)

    character = args.character
    if not character and _is_classmod_type(args.type):
        character = ctx.config.character
        note("no --character given for a class-mod search; using %s (config)" % character)
    if args.no_verify:
        note("--no-verify: element labels come from the database and are not checked against the serials")

    result = catalog.search(SearchQuery(
        query=args.query, type=args.type, element=args.element, manufacturer=args.manufacturer,
        rarity=args.rarity, character=character, limit=args.limit,
        verify_element=not args.no_verify, include_unowned=args.include_unowned))
    rows = [_relevel_entry(codec, e, level) for e in result.entries]

    hidden = []
    if result.hidden_by_pack:
        rules = ctx.use("rules")
        hidden = [(pack, rules.pack_label(pack), n) for pack, n in sorted(result.hidden_by_pack.items())]
    dropped = result.dropped_element_mismatch

    if args.json:
        emit_json({
            "count": len(rows), "level": level, "results": rows,
            "hidden": [{"pack": p, "label": label, "count": n} for p, label, n in hidden],
            "dropped_element_mismatch": dropped,
        })
        return EXIT_OK

    if not rows:
        out("No matches.")
    for i, row in enumerate(rows, 1):
        lvl = ("Lv%s" % row["level"]) if row["level"] is not None else "Lv?"
        out("%2d. %-34s %-10s %-9s %-10s %s" % (
            i, row["name"][:34], row["manufacturer"], element_label(row["element"]), lvl, row["serial"]))
        for w in row["warnings"]:
            out("      warning: %s" % w)
    # Never truncate silently: say what was filtered and why.
    footer = hidden_lines(hidden)
    if dropped:
        footer.append("%d dropped: database element label disagreed with the serial "
                      "(pass --no-verify to see them)" % dropped)
    if footer:
        out()
        for line in footer:
            out(line)
    return EXIT_OK


# ---- codec commands ------------------------------------------------------------------------------

def cmd_decode(ctx: Context, args: Any) -> int:
    codec = ctx.use("codec")
    blocks = codec.decode(_serial(args.serial))
    data = {"parts": codec.parts_string(blocks), "level": codec.get_level(blocks),
            "category_id": codec.get_category_id(blocks)}
    if args.json:
        emit_json(data)
    else:
        out("parts: %s" % data["parts"])
        out("level: %s" % data["level"])
        out("category index: %s" % data["category_id"])
    return EXIT_OK


def cmd_relevel(ctx: Context, args: Any) -> int:
    codec = ctx.use("codec")
    level = args.level if args.level is not None else ctx.config.level
    out(codec.relevel(_serial(args.serial), level))
    return EXIT_OK


# ---- ops commands --------------------------------------------------------------------------------

def cmd_identify(ctx: Context, args: Any) -> int:
    ops = ctx.use("ops")
    info = ops.describe(_serial(args.serial))
    estimate = ops.rarity_estimate(info)
    if args.json:
        data = info.to_dict()
        if args.odds:
            data["odds"] = estimate
        emit_json(data)
        return EXIT_OK
    out("%-14s %s" % ("Item:", info.display_name or "?"))
    out("%-14s %s (category %s)" % ("Category:", info.category or "?", info.category_id))
    out("%-14s %s" % ("Level:", info.level))
    out("%-14s %s" % ("Rarity:", info.rarity or "?"))
    out("%-14s %s" % ("Element:", element_label(info.element)))
    out("%-14s %s%s" % ("Content:", info.content_pack_label or "Base game",
                        "" if info.owned else "   [NOT OWNED]"))
    for rarity, name in info.other_components:
        out("%-14s %s - %s" % ("Also carries:", rarity, name or "?"))
    odds = ops.format_odds(estimate)
    if odds:
        out("%-14s %s" % ("Drop odds:", odds))
    out()
    out("Parts (position: name):")
    for i, part in enumerate(info.parts):
        out("  %2d: %s" % (i, part.label()))
    for w in info.warnings:
        out()
        out("warning: %s" % w)
    return EXIT_OK


def _describe_line(ops, serial: str) -> str:
    info = ops.describe(serial)
    return "-> %s, %s, level %s" % (info.display_name or "?", element_label(info.element), info.level)


def cmd_set_element(ctx: Context, args: Any) -> int:
    ops = ctx.use("ops")
    serial = _serial(args.serial)
    info = ops.describe(serial)
    # ops.set_element would happily insert an element part into a shield (legacy behaviour kept);
    # the contract makes the caller responsible for offering it for weapons only.
    if info.manifest_ok and info.element is None:
        raise CliError("refused: %s (%s) is gear and has no element; set-element is for weapons"
                       % (info.display_name or "this item", info.category or "unknown category"), EXIT_USAGE)
    new = ops.set_element(serial, args.element)
    if args.level is not None:
        new = ctx.use("codec").relevel(new, args.level)
    out(new)
    line = _describe_line(ops, new)
    if new == serial:
        line += "  (serial unchanged)"
    err(line)
    return EXIT_OK


def cmd_reseed(ctx: Context, args: Any) -> int:
    ops = ctx.use("ops")
    serial = _serial(args.serial)
    old = ops.get_seed(serial)
    new = ops.set_seed(serial, args.seed)
    out(new)
    err("-> seed %s (was %s)" % (args.seed, old if old is not None else "none"))
    return EXIT_OK


def cmd_diff(ctx: Context, args: Any) -> int:
    ops = ctx.use("ops")
    rows = list(ops.diff(_serial(args.a), _serial(args.b)))
    if args.json:
        emit_json({"identical": not rows, "differences": rows})
        return EXIT_OK
    if not rows:
        out("Identical.")
        return EXIT_OK
    out("%-14s %-34s %s" % ("FIELD", "A", "B"))
    for r in rows:
        out("%-14s %-34s %s" % (r["field"], str(r["a"])[:34], r["b"]))
    return EXIT_OK


def _positions(text: str) -> List[int]:
    try:
        values = [int(x) for x in text.replace(" ", "").split(",") if x != ""]
    except ValueError:
        values = []
    if not values:
        raise CliError("--positions must be comma-separated part numbers from `identify`, e.g. 3,4", EXIT_USAGE)
    return values


def cmd_swap(ctx: Context, args: Any) -> int:
    ops = ctx.use("ops")
    rules = ctx.use("rules")
    positions = _positions(args.positions)
    try:
        new = ops.swap_parts(_serial(args.base), _serial(args.source), positions, allow_cross=args.allow_cross)
    except SerialError as ex:
        raise CliError("swap refused: %s" % str(ex).replace("allow_cross=True", "--allow-cross"), EXIT_USAGE)
    out(new)
    info = ops.describe(new)
    err("-> %s, %s, level %s" % (info.display_name or "?", element_label(info.element), info.level))
    for w in list(info.warnings) + list(rules.validate(new)):
        warn(w)
    note("structural checks only; part compatibility is not verified, so this is not a guarantee "
         "the item is valid in game")
    return EXIT_OK


def cmd_validate(ctx: Context, args: Any) -> int:
    rules = ctx.use("rules")
    problems = list(rules.validate(_serial(args.serial)))
    if args.json:
        emit_json({"serial": _serial(args.serial), "ok": not problems, "problems": problems})
    elif not problems:
        out("OK - passed structural checks (this is not a guarantee the item is valid in game).")
    else:
        for p in problems:
            out("problem: %s" % p)
    return EXIT_CHECK_FAILED if problems else EXIT_OK


# ---- build ---------------------------------------------------------------------------------------

_STR_FIELDS = ("group", "serial", "query", "type", "element", "manufacturer", "rarity", "character",
               "note", "display_name", "label", "name", "label_name")
_SEARCH_FIELDS = ("query", "type", "element", "manufacturer", "rarity", "character")
_KNOWN_KEYS = set(LoadoutRequest.__dataclass_fields__) | {"label_name"}


def _load_spec(arg: str) -> Any:
    if arg == "-":
        text, origin = sys.stdin.read(), "stdin"
    elif arg.startswith("@"):
        origin = arg[1:]
        try:
            text = Path(os.path.expanduser(origin)).read_text(encoding="utf-8-sig")
        except OSError as ex:
            raise CliError("cannot read spec file %s: %s" % (origin, ex.strerror or ex), EXIT_USAGE)
        except UnicodeDecodeError as ex:
            raise CliError("spec file %s is not UTF-8 text: %s" % (origin, ex), EXIT_USAGE)
    else:
        text, origin = arg, "--spec"
    try:
        return json.loads(text)
    except ValueError as ex:
        hint = " (tip: --spec @file.json avoids shell quoting problems)" if origin == "--spec" else ""
        raise CliError("spec (%s) is not valid JSON: %s%s" % (origin, ex, hint), EXIT_USAGE)


def _parse_requests(raw: Any, default_character: str) -> List[LoadoutRequest]:
    if not isinstance(raw, list):
        raise CliError("spec must be a JSON array of objects", EXIT_USAGE)
    if not raw:
        raise CliError("spec is empty: it must list at least one item", EXIT_USAGE)
    requests: List[LoadoutRequest] = []
    for i, item in enumerate(raw, 1):
        where = "spec entry %d: " % i
        if not isinstance(item, dict):
            raise CliError(where + "must be a JSON object", EXIT_USAGE)
        for key in _STR_FIELDS:
            if item.get(key) is not None and not isinstance(item[key], str):
                raise CliError(where + "%r must be a string" % key, EXIT_USAGE)
        unknown = sorted(k for k in item if k not in _KNOWN_KEYS)
        if unknown:
            warn(where + "ignoring unknown key(s): %s" % ", ".join(unknown))
        try:
            req = LoadoutRequest.from_dict(item)
        except (TypeError, ValueError) as ex:
            raise CliError(where + "invalid (%s)" % ex, EXIT_USAGE)
        if req.count < 1:
            raise CliError(where + "count must be >= 1, got %d" % req.count, EXIT_USAGE)
        if req.serial and req.serial != req.serial.strip():
            req = dataclasses.replace(req, serial=req.serial.strip())
        if not req.serial:
            if not any((getattr(req, f) or "").strip() for f in _SEARCH_FIELDS):
                raise CliError(where + "needs a 'serial' or at least one search field (%s)"
                               % ", ".join(_SEARCH_FIELDS), EXIT_USAGE)
            _check_element(req.element, where)
            if not req.character and _is_classmod_type(req.type):
                note(where + "class mod without a character; using %s (config)" % default_character)
                req = dataclasses.replace(req, character=default_character)
        requests.append(req)
    return requests


def _item_dict(item) -> Dict[str, Any]:
    return {
        "name": item.legendary_name or item.name, "display_name": item.shown_name, "group": item.group,
        "category": item.category, "element": item.element, "rarity": item.rarity,
        "level": item.level, "serial": item.serial, "warnings": list(item.warnings),
    }


def _summary(loadout: Loadout, html_path: str, text_path: str) -> Dict[str, Any]:
    warnings = set(loadout.warnings)
    for item in loadout.items:
        warnings.update(item.warnings)
    return {
        "title": loadout.title, "level": loadout.level, "count": len(loadout.items),
        "html": os.path.abspath(html_path), "plain": os.path.abspath(text_path),
        "items": [_item_dict(it) for it in loadout.items],
        "unmatched": list(loadout.unmatched),
        "warnings": sorted(warnings),
    }


def _report_loadout(loadout: Loadout) -> None:
    """Human form of what the JSON summary also carries, on stderr."""
    for entry in loadout.unmatched:
        err("unmatched: %s" % entry)
    for w in loadout.warnings:
        warn(w)
    for item in loadout.items:
        for w in item.warnings:
            warn("%s: %s" % (item.shown_name, w))


def cmd_build(ctx: Context, args: Any) -> int:
    requests = _parse_requests(_load_spec(args.spec), ctx.config.character)
    level = _effective_level(ctx, args)
    builder = ctx.use("builder")
    render = ctx.use("render")
    title = args.title or "Borderlands 4 Loadout"
    try:
        loadout = builder.build(requests, level=level, title=title)
    except NotImplementedError as ex:
        raise CliError("%s (%s)" % (ex, DOCTOR_HINT), EXIT_UNAVAILABLE)

    if not loadout.items:
        err("error: no items resolved from spec")
        _report_loadout(loadout)
        return EXIT_NOTHING

    try:
        html_path, text_path = render.write(loadout, args.out, args.plain)
    except ForgeError as ex:
        raise CliError("cannot write output: %s" % ex, EXIT_USAGE)
    emit_json(_summary(loadout, html_path, text_path))
    _report_loadout(loadout)
    return EXIT_OK


# ---- serve ---------------------------------------------------------------------------------------

def cmd_serve(ctx: Context, args: Any) -> int:
    """Run the local web UI. The web layer is imported here, so no other command ever loads it."""
    from .. import web
    if args.host not in ("127.0.0.1", "localhost", "::1") and not getattr(args, "allow_remote", False):
        raise CliError("refusing to listen on %r: only loopback (127.0.0.1, localhost, ::1) is allowed by default. "
                       "The web UI has no login, so a reachable port is open to anyone on that network. "
                       "Pass --allow-remote only if you understand and accept that." % args.host, EXIT_USAGE)
    try:
        return web.serve(ctx.forge, host=args.host, port=args.port, open_browser=args.open, quiet=args.quiet)
    except web.PortInUse as ex:
        raise CliError(str(ex), EXIT_UNAVAILABLE)
    except web.ServerStartError as ex:
        raise CliError(str(ex), EXIT_USAGE)


# ---- doctor --------------------------------------------------------------------------------------

def cmd_doctor(ctx: Context, args: Any) -> int:
    rows = diagnose(ctx.forge)
    print(json.dumps(rows, indent=1) if args.json else format_report(rows, args.verbose))
    return EXIT_OK if doctor_ok(rows) else EXIT_CHECK_FAILED
