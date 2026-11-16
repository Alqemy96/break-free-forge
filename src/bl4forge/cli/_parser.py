"""Argument definitions. Every sub-command names the commands.py function that runs it and the
modules it needs (`needs`): the Forge only starts those plus their dependencies, so an unrelated
sick module cannot stop, say, `decode`. `needs=None` means everything (doctor).

DISCLOSURE (what this code does)
  Reads: nothing. Writes: nothing (declares the command line). Network: none. Risk: see DISCLOSURE.md for what each command does.
"""
from __future__ import annotations

import argparse

from .. import __version__
from . import _commands as cmd
from . import _lootpak_cmds as lootcmd
from . import _save_cmds as savecmd
from ._core import (EXIT_CHECK_FAILED, EXIT_FAILED, EXIT_NOTHING, EXIT_OK, EXIT_UNAVAILABLE,
                    EXIT_USAGE)

EPILOG = """\
exit codes:
  %d  ok
  %d  doctor found an unhealthy module / validate found structural problems
  %d  bad usage: arguments, spec, serial, config, or a refused operation (e.g. cross-category swap)
  %d  build: nothing in the spec resolved
  %d  a needed module is unavailable (see `bl4forge doctor`) or its data is missing
  %d  any other failure (re-run with --debug for the traceback)

defaults come from config.toml (level, character, owned packs); override the file with
--config PATH or the BL4FORGE_CONFIG environment variable.
""" % (EXIT_OK, EXIT_CHECK_FAILED, EXIT_USAGE, EXIT_NOTHING, EXIT_UNAVAILABLE, EXIT_FAILED)


def _level(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("level must be an integer from 1 to 100, got %r" % text)
    if not 1 <= value <= 100:
        raise argparse.ArgumentTypeError("level must be from 1 to 100, got %d" % value)
    return value


def _limit(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("limit must be a whole number >= 1, got %r" % text)
    if value < 1:
        raise argparse.ArgumentTypeError("limit must be >= 1, got %d" % value)
    return value


def _port(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer from 0 to 65535, got %r" % text)
    if not 0 <= value <= 65535:
        raise argparse.ArgumentTypeError("port must be from 0 to 65535, got %d" % value)
    return value


def build_parser() -> argparse.ArgumentParser:
    # Global flags are accepted before AND after the command (SUPPRESS keeps an absent flag from
    # overwriting one given in the other position).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", dest="config_path", metavar="PATH", default=argparse.SUPPRESS,
                        help="config.toml to use (default: $BL4FORGE_CONFIG, else <project>/config.toml)")
    common.add_argument("--debug", action="store_true", default=argparse.SUPPRESS,
                        help="show tracebacks for errors")

    parser = argparse.ArgumentParser(
        prog="bl4forge", parents=[common], epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Borderlands 4 loadout forge: search the serial database, identify and modify "
                    "serials, build code sheets.")
    parser.add_argument("--version", action="version", version="bl4forge " + __version__)
    sub = parser.add_subparsers(dest="cmd", metavar="command", required=True)

    def add(name, func, needs, help_, **kw):
        sp = sub.add_parser(name, parents=[common], help=help_, description=help_, **kw)
        sp.set_defaults(func=func, needs=needs)
        return sp

    sp = add("catalog", cmd.cmd_catalog, ("catalog",), "overview of the serial database")
    sp.add_argument("--json", action="store_true")

    sp = add("search", cmd.cmd_search, ("catalog", "rules", "codec"),
             "search the database (re-leveled to the configured level unless --no-relevel)")
    sp.add_argument("--query", help="substring of the item name")
    sp.add_argument("--type", help="pistol, shotgun, smg, assault_rifle/ar, sniper, heavy, shield, "
                                   "classmod, repkit, gadget/grenade, enhancement")
    sp.add_argument("--element", help="cryo, fire, radiation, shock/electric, corrosive, impact")
    sp.add_argument("--manufacturer")
    sp.add_argument("--rarity", help="legendary, epic, ...")
    sp.add_argument("--character", help="gravitar, dark_siren, exo_soldier, paladin (class mods; "
                                        "defaults to the configured character for --type classmod)")
    sp.add_argument("--limit", type=_limit, default=25)
    sp.add_argument("--level", type=_level, help="re-level results to this level (default: config level)")
    sp.add_argument("--no-relevel", action="store_true",
                    help="leave codes at the database's stored level")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--include-unowned", action="store_true", dest="include_unowned",
                    help="also show items needing DLC outside the owned packs")
    sp.add_argument("--no-verify", action="store_true", dest="no_verify",
                    help="trust the database's element label instead of the decoded serial")

    sp = add("decode", cmd.cmd_decode, ("codec",), "decode a serial into its raw blocks")
    sp.add_argument("--serial", required=True)
    sp.add_argument("--json", action="store_true")

    sp = add("relevel", cmd.cmd_relevel, ("codec",), "same item at another level")
    sp.add_argument("--serial", required=True)
    sp.add_argument("--level", type=_level, help="target level (default: config level)")

    sp = add("identify", cmd.cmd_identify, ("ops",), "what is this serial, really? (read from the bitstream)")
    sp.add_argument("--serial", required=True)
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--odds", action="store_true",
                    help="with --json: add the drop-odds estimate under the key 'odds'")

    sp = add("set-element", cmd.cmd_set_element, ("ops", "codec"), "change or strip a weapon's element")
    sp.add_argument("--serial", required=True)
    sp.add_argument("--element", required=True,
                    help="cryo, fire, shock, corrosive, radiation, or impact to remove")
    sp.add_argument("--level", type=_level, help="also re-level the result")

    sp = add("reseed", cmd.cmd_reseed, ("ops",), "reroll stat variance, keeping parts and level")
    sp.add_argument("--serial", required=True)
    sp.add_argument("--seed", type=int, required=True)

    sp = add("diff", cmd.cmd_diff, ("ops",), "compare two serials")
    sp.add_argument("--a", required=True)
    sp.add_argument("--b", required=True)
    sp.add_argument("--json", action="store_true")

    sp = add("swap", cmd.cmd_swap, ("ops", "rules"), "copy parts from one serial into another")
    sp.add_argument("--base", required=True)
    sp.add_argument("--source", required=True)
    sp.add_argument("--positions", required=True,
                    help="comma-separated part positions from `identify`, e.g. 3,4")
    sp.add_argument("--allow-cross", action="store_true", dest="allow_cross",
                    help="permit swapping between different item categories (usually wrong)")

    sp = add("validate", cmd.cmd_validate, ("rules",), "structural check of a serial (not an in-game guarantee)")
    sp.add_argument("--serial", required=True)
    sp.add_argument("--json", action="store_true")

    sp = add("build", cmd.cmd_build, ("builder", "render"), "build a loadout: HTML code sheet + plain-text list")
    sp.add_argument("--spec", required=True, help="JSON array: inline, @file.json, or - for stdin")
    sp.add_argument("--out", required=True, help="HTML file to write")
    sp.add_argument("--plain", help="plain-text file (default: --out with .txt)")
    group = sp.add_mutually_exclusive_group()
    group.add_argument("--level", type=_level, help="re-level every code (default: config level)")
    group.add_argument("--no-relevel", action="store_true", help="leave codes at their stored level")
    sp.add_argument("--title")

    # ---- save files: open, list, patch, write a copy -------------------------------------------
    def save_args(sp, writes=False):
        sp.add_argument("--file", required=True, help="the .sav file (read only; it is never modified)")
        sp.add_argument("--platform", choices=("ps5", "pc"), default="ps5", help="save format (default ps5)")
        sp.add_argument("--steam-id", dest="steam_id", help="Steam ID, required for --platform pc")
        if writes:
            sp.add_argument("--out", help="where to write the edited COPY (never the source file)")
            sp.add_argument("--dry-run", action="store_true", dest="dry_run",
                            help="show the changed line(s) and write nothing")
            sp.add_argument("--overwrite", action="store_true", help="replace an existing --out copy")

    sp = add("save-open", savecmd.cmd_save_open, ("save", "ops"),
             "open a save: character, currencies and every item with its decoded name")
    save_args(sp)
    sp.add_argument("--json", action="store_true")

    sp = add("save-items", savecmd.cmd_save_items, ("save", "ops"), "list a save's inventory items")
    save_args(sp)
    sp.add_argument("--area", choices=("backpack", "equipped", "lostloot"))
    sp.add_argument("--serials", action="store_true", help="print bare serials, one per line")
    sp.add_argument("--json", action="store_true")

    sp = add("save-decrypt", savecmd.cmd_save_decrypt, ("save",), "write a save's YAML text to a file")
    save_args(sp)
    sp.add_argument("--out", required=True, help="YAML file to write")
    sp.add_argument("--overwrite", action="store_true")

    sp = add("save-set-currency", savecmd.cmd_save_set_currency, ("save",),
             "set a currency (one line changes); writes an edited copy")
    save_args(sp, writes=True)
    sp.add_argument("--name", required=True, help="cash or eridium (any currency the save already has)")
    sp.add_argument("--value", type=int, required=True)

    sp = add("save-set-point-pool", savecmd.cmd_save_set_point_pool, ("save",),
             "set a shared point pool in a PROFILE save (e.g. echotokenprogresspoints); writes an edited copy")
    save_args(sp, writes=True)
    sp.add_argument("--name", required=True, help="a pool the profile already has, e.g. echotokenprogresspoints")
    sp.add_argument("--value", type=int, required=True, help="0..2147483647; TOTAL earned, not available")

    sp = add("save-set-level", savecmd.cmd_save_set_level, ("save",),
             "set the character level and/or XP points; writes an edited copy")
    save_args(sp, writes=True)
    sp.add_argument("--level", type=_level)
    sp.add_argument("--xp", type=int, help="XP points of the character")

    sp = add("save-set-serial", savecmd.cmd_save_set_serial, ("save", "ops"),
             "replace one item's serial (it must decode); writes an edited copy")
    save_args(sp, writes=True)
    sp.add_argument("--ref", required=True, help="item address from save-items, e.g. backpack/slot_3")
    sp.add_argument("--serial", required=True)

    # ---- loot pak: plan / build a PS5 loot pak from a TOML config (no console or network code) ----------
    sp = add("lootpak-plan", lootcmd.cmd_lootpak_plan, ("lootpak",),
             "print the plan for a loot-pak config (writes nothing)")
    sp.add_argument("lootpak_config", metavar="CONFIG", help="the loot-pak TOML (see examples/lootpak/)")

    sp = add("lootpak-build", lootcmd.cmd_lootpak_build, ("lootpak",),
             "build a loot pak into a NEW folder and verify it (decode-diff gate)")
    sp.add_argument("lootpak_config", metavar="CONFIG", help="the loot-pak TOML (see examples/lootpak/)")
    sp.add_argument("outdir", metavar="OUTDIR", help="a folder that does not exist yet (never the base's folder)")

    sp = add("serve", cmd.cmd_serve, None, "run the local web UI (listens on 127.0.0.1 only unless --allow-remote)")
    sp.add_argument("--host", default="127.0.0.1",
                    help="address to listen on (default 127.0.0.1 = this machine only; any other address needs "
                         "--allow-remote)")
    sp.add_argument("--allow-remote", action="store_true", dest="allow_remote",
                    help="RISKY: permit --host to be an address other than loopback. The UI has no login and can "
                         "decrypt and re-encrypt saves sent to it; anyone who can reach the port can use it")
    sp.add_argument("--port", type=_port, default=8734, help="port to listen on (default 8734; 0 = any free port)")
    sp.add_argument("--open", action="store_true", help="open the UI in the default browser")
    sp.add_argument("--quiet", action="store_true", help="do not log one line per request to stderr")

    sp = add("doctor", cmd.cmd_doctor, None, "health-check every module")
    sp.add_argument("-v", "--verbose", action="store_true")
    sp.add_argument("--json", action="store_true")

    return parser
