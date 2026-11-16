"""Loot-pak commands (outer layer): no domain logic, only calls into the `lootpak` cell.

`lootpak-plan CONFIG` prints the plan and writes nothing. `lootpak-build CONFIG OUTDIR` builds into a NEW
folder and verifies the result (decode-diff gate). Neither command touches a console or the network.


DISCLOSURE (what this code does)
  Reads: a loot-pak TOML config and the base game-data files it names. Writes: `lootpak-plan` writes only a scratch folder that is deleted; `lootpak-build` writes into a NEW, empty output folder (an existing folder is refused). Network: none. Risk: RUNS external programs (ncstool, bl4, uextract) whose paths are set in config.toml; only point those at tools you built or trust, and never at a config.toml you did not write yourself. The output is game data (a pak) and its effect in game is unproven.
"""
from __future__ import annotations

from typing import Any

from ._core import Context, EXIT_OK, out


def cmd_lootpak_plan(ctx: Context, args: Any) -> int:
    from ..modules.lootpak._plan import format_plan
    cell = ctx.use("lootpak")
    plan = cell.plan(cell.load_config(args.lootpak_config))
    for line in format_plan(plan):
        out(line)
    return EXIT_OK


def cmd_lootpak_build(ctx: Context, args: Any) -> int:
    cell = ctx.use("lootpak")
    cell.log = out
    res = cell.build(cell.load_config(args.lootpak_config), args.outdir)
    out("manifest %s" % res.manifest_path)
    out("regen    %s" % res.regen_path)
    out("sha256   %s" % res.pak_sha256)
    return EXIT_OK
