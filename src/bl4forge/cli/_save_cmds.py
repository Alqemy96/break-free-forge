"""Save-file commands (outer layer). Same rules as _commands.py: no domain logic, only port calls.

Every command that changes a save writes a COPY (`--out`, never the source) with the original's
sha256 recorded next to it, and re-reads the copy to prove it decrypts to exactly the patched YAML.


DISCLOSURE (what this code does)
  Reads: the save file named by --file (read only, never modified). Writes: `save-decrypt` writes the decrypted YAML to --out; the `save-set-*` commands write an edited COPY to --out plus a `<out>.bl4forge.json` sidecar holding the original's sha256 (refused if --out is the source; refused if --out exists unless --overwrite). --dry-run writes nothing. Network: none. Risk: an edited save can corrupt a character or trip server-side checks if you play online; the decrypted YAML contains your account-bound data, so do not share it. Close the game before copying an edited save back, and keep your own backup of the original.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.errors import SaveError, SerialError
from ._core import CliError, Context, EXIT_OK, EXIT_USAGE, emit_json, note, out, warn


def _read(args: Any) -> Tuple[Path, bytes]:
    path = Path(args.file)
    if not path.is_file():
        raise CliError("no such save file: %s" % args.file, EXIT_USAGE)
    return path, path.read_bytes()


def _decrypt(ctx: Context, args: Any, raw: bytes) -> str:
    save = ctx.use("save")
    if args.platform == "pc":
        if not args.steam_id:
            raise CliError("--steam-id is required for a PC save", EXIT_USAGE)
        return save.decrypt_pc(raw, args.steam_id)
    return save.decrypt_ps5(raw)


def _encrypt(ctx: Context, args: Any, yaml_text: str) -> bytes:
    save = ctx.use("save")
    return save.encrypt_pc(yaml_text, args.steam_id) if args.platform == "pc" else save.encrypt_ps5(yaml_text)


def describe_items(ctx: Context, yaml_text: str) -> List[Dict[str, Any]]:
    """Every save item with its decoded facts (name, level, rarity, category) from the ops cell.
    A serial that will not decode is reported with `error`, never dropped."""
    save, ops = ctx.use("save"), ctx.use("ops")
    rows: List[Dict[str, Any]] = []
    for it in save.list_items(yaml_text):
        row: Dict[str, Any] = dict(it.to_dict(), name=None, level=None, rarity=None, category=None,
                                   element=None, warnings=[], error=None)
        try:
            info = ops.describe(it.serial)
            row.update(name=info.display_name, level=info.level, rarity=info.rarity,
                       category=info.category, element=info.element, warnings=list(info.warnings))
        except SerialError as ex:
            row["error"] = str(ex)
        rows.append(row)
    return rows


def _item_lines(rows: List[Dict[str, Any]]) -> List[str]:
    out_lines = ["%-17s %-4s %-9s %-10s %s" % ("ref", "lvl", "rarity", "element", "name")]
    for r in rows:
        name = r["name"] or ("?  (%s)" % r["error"] if r["error"] else "?")
        out_lines.append("%-17s %-4s %-9s %-10s %s" % (
            r["ref"], r["level"] if r["level"] is not None else "-", r["rarity"] or "-",
            r["element"] or "-", name))
    return out_lines


def cmd_save_open(ctx: Context, args: Any) -> int:
    path, raw = _read(args)
    save = ctx.use("save")
    yaml_text = _decrypt(ctx, args, raw)
    summ = save.summary(yaml_text)
    rows = describe_items(ctx, yaml_text)
    pool = save.shared_pool_report(yaml_text)
    if args.json:
        emit_json({"file": str(path), "sha256": save.sha256(raw), "platform": args.platform,
                   "yaml_bytes": len(yaml_text.encode("utf-8")), "summary": summ, "items": rows,
                   "echo_tokens": pool})
        return EXIT_OK
    out("File:       %s (%s, sha256 %s)" % (path, args.platform, save.sha256(raw)))
    if summ["name"] is None and not rows:
        out("This looks like a profile save: no character or items in it.")
    else:
        out("Character:  %s (%s), level %s, %s XP" % (summ["name"], summ["class"], summ["level"], summ["points"]))
        out("Currencies: " + ", ".join("%s %s" % kv for kv in summ["currencies"].items()))
    if pool:
        out("Echo tokens: %s earned, %s spent (sdu_upgrades), %s available" % (
            pool["value"], pool["spent"], pool["available"]))
    if rows:
        out("")
        for line in _item_lines(rows):
            out(line)
    return EXIT_OK


def cmd_save_items(ctx: Context, args: Any) -> int:
    _path, raw = _read(args)
    rows = describe_items(ctx, _decrypt(ctx, args, raw))
    if args.area:
        rows = [r for r in rows if r["area"] == args.area]
    if args.json:
        emit_json(rows)
    elif args.serials:
        for r in rows:
            out(r["serial"])
    else:
        for line in _item_lines(rows):
            out(line)
    return EXIT_OK


def cmd_save_decrypt(ctx: Context, args: Any) -> int:
    path, raw = _read(args)
    yaml_text = _decrypt(ctx, args, raw)
    dest = Path(args.out)
    if dest.exists() and not args.overwrite:
        raise CliError("destination already exists: %s (use --overwrite)" % args.out, EXIT_USAGE)
    if dest.resolve() == path.resolve():
        raise CliError("refusing to write over the source save", EXIT_USAGE)
    dest.write_bytes(yaml_text.encode("utf-8"))
    out("wrote %s (%d bytes of YAML)" % (dest, len(yaml_text.encode("utf-8"))))
    return EXIT_OK


def _commit(ctx: Context, args: Any, path: Path, raw: bytes, before: str, after: str) -> int:
    """Show the changed lines; unless --dry-run, wrap the patched YAML and write it as a copy."""
    save = ctx.use("save")
    changes = save.changed_lines(before, after)
    for n, old, new in changes:
        out("line %d:" % n)
        out("  - %s" % old.strip())
        out("  + %s" % new.strip())
    out("%d line(s) changed" % len(changes))
    if not changes:
        note("nothing to write: the save already has that value")
        return EXIT_OK
    if args.dry_run:
        out("dry run: nothing written")
        return EXIT_OK
    if not args.out:
        raise CliError("--out is required (saves are only ever written as a copy), or use --dry-run", EXIT_USAGE)
    blob = _encrypt(ctx, args, after)
    if _decrypt(ctx, args, blob) != after:
        raise SaveError("internal check failed: the re-wrapped save does not decrypt to the patched YAML")
    rec = save.write_copy(str(path), args.out, blob, overwrite=args.overwrite)
    out("wrote %s (%d bytes)" % (rec["dest"], rec["dest_bytes"]))
    out("source sha256 %s (unchanged)" % rec["source_sha256"])
    out("copy   sha256 %s" % rec["dest_sha256"])
    return EXIT_OK


def cmd_save_set_currency(ctx: Context, args: Any) -> int:
    path, raw = _read(args)
    before = _decrypt(ctx, args, raw)
    after = ctx.use("save").set_currency(before, args.name, args.value)
    return _commit(ctx, args, path, raw, before, after)


def cmd_save_set_point_pool(ctx: Context, args: Any) -> int:
    path, raw = _read(args)
    save = ctx.use("save")
    before = _decrypt(ctx, args, raw)
    after = save.set_shared_point_pool(before, args.name, args.value)
    rep = save.shared_pool_report(after, args.name)
    if rep:
        out("%s: %s earned, %s spent, %s available after this edit" % (
            rep["name"], rep["value"], rep["spent"], rep["available"]))
    return _commit(ctx, args, path, raw, before, after)


def cmd_save_set_level(ctx: Context, args: Any) -> int:
    if args.level is None and args.xp is None:
        raise CliError("give --level and/or --xp", EXIT_USAGE)
    path, raw = _read(args)
    before = _decrypt(ctx, args, raw)
    if args.level is not None and args.xp is None:
        warn("level changed without XP points: the XP-to-level table is not checked here, so the game "
             "may re-derive one from the other (UNVERIFIED)")
    after = ctx.use("save").set_progress(before, level=args.level, points=args.xp)
    return _commit(ctx, args, path, raw, before, after)


def cmd_save_set_serial(ctx: Context, args: Any) -> int:
    path, raw = _read(args)
    before = _decrypt(ctx, args, raw)
    serial = args.serial.strip()
    info = ctx.use("ops").describe(serial)                     # raises SerialError: never write junk
    out("new item: %s, level %s, %s" % (info.display_name or "?", info.level, info.rarity or "?"))
    after = ctx.use("save").set_serial(before, args.ref, serial)
    return _commit(ctx, args, path, raw, before, after)
