"""lootpak: build a PS5 loot pak from one TOML config (value retargets of gbx_ue_data_table0), with proof.

A leaf cell: it needs no neighbour and never touches the save cell. Config parsing is `_config.py`, finding the
leaves `_locate.py`, the plan `_plan.py`, the pipeline and decode-diff gate `_build.py`, the write protection
`_guard.py`, and the only code that runs an external program `_tools.py` (replaceable by a fake). This file is the
cell: the `LootPakPort` methods and `health()`. Read CONTRACT.md in this directory for the rules.

No console or network code lives here. Installing a pak on the PS5 stays a separate, human step.


DISCLOSURE (what this code does)
  Reads: a loot-pak TOML config, the base game files it names, and config.toml [lootpak]. Writes: scratch folders (deleted) and, for build, a NEW output folder only (never the base's folder, an existing folder, or one under a 'backups' folder). Network: none. Risk: RUNS the external programs named in config.toml [lootpak] through subprocess (argument list, no shell). Those paths come from your own config.toml: treat it as executable configuration and never use one from an untrusted source.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, List, Optional

from ...core.errors import ConfigError
from ...core.module import Module, ModuleContext
from ...core.ports import LootPakPort
from ...core.types import HealthCheck, HealthReport
from . import _build, _config, _decode, _guard, _leaves, _plan, _tools
from ._build import BuildResult
from ._config import LootConfig
from ._plan import Plan
from ._tools import SubprocessTools, Tools

_HEALTH_DECODE = """File: x
  Record 0:
    table_enemydrops = {
      data: [{
          row_name: Chump
          row_value: {
            guns_probability: 0.050000
            rarity_modifier: {
              commonmodifier: 0.750000
            }
          }
        }]
      gbx_ue_data_table: Table_EnemyDrops
      row_struct: Asset'/Game/X.X'
    }
"""
_HEALTH_LOG = ("BINOFF 8\nREMAPB count=0 vbw=0 ibw=0 values=[]\n"
               "LEAF bitpos=10 bits=13 raw=1 mapped=1 val=0.050000\n")


class LootPakModule(Module):
    name = "lootpak"
    purpose = "Build a PS5 loot pak from a TOML config (value retargets only), with a decode-diff proof."
    requires = ()
    port = LootPakPort

    def __init__(self, ctx: ModuleContext, tools: Optional[Tools] = None):
        super().__init__(ctx)
        self._tools = tools
        self.log: Callable[[str], None] = lambda line: None     # the CLI sets this to print progress

    # ---- tools (lazy: a missing [lootpak] section only matters when you build) ----
    @property
    def tools(self) -> Tools:
        if self._tools is None:
            self._tools = SubprocessTools.from_settings(self.config.lootpak)
        return self._tools

    @tools.setter
    def tools(self, value: Tools) -> None:
        self._tools = value

    def modwork(self) -> Optional[Path]:
        v = self.config.lootpak.get("modwork")
        return Path(v) if v else None

    def protected(self) -> List[Path]:
        raw = self.config.lootpak.get("protected_dirs", "")
        return [Path(p) for p in raw.split(";") if p.strip()]

    # ---- port ----
    def load_config(self, path: str) -> LootConfig:
        return _config.load_config_file(path, self.modwork())

    def plan(self, config: LootConfig) -> Plan:
        with tempfile.TemporaryDirectory(prefix="lootpak-plan-") as scratch:
            return _plan.make_plan(config, self.tools, Path(scratch))

    def build(self, config: LootConfig, out_dir: str) -> BuildResult:
        return _build.build(config, Path(out_dir), self.tools, self.log, self.protected())

    # ---- self-check ----
    def health(self) -> HealthReport:
        checks: List[HealthCheck] = []
        try:
            tables = _decode.parse_decode(_HEALTH_DECODE)
            row = tables["table_enemydrops"][0].rows[0]
            checks.append(HealthCheck("decode parser reads row and nested leaf",
                                      [lf.path for lf in row.leaves] == ["guns_probability",
                                                                         "rarity_modifier.commonmodifier"], ""))
            log = _leaves.parse_leaf_log(_HEALTH_LOG)
            checks.append(HealthCheck("leaf log parser", log.binoff == 8 and log.leaves[0].bitpos == 10, ""))
            checks.append(HealthCheck("numbers spelled the NCS way", _config.format_value(0.6) == "0.600000", ""))
            raised = False
            try:
                _config.format_value(0.1234567)
            except ConfigError:
                raised = True
            checks.append(HealthCheck("over-precise value refused", raised, ""))
            checks.append(HealthCheck("backups path refused",
                                      _guard.under_backups(Path("/x/backups/y")), ""))
        except Exception as ex:  # health() must never raise
            checks.append(HealthCheck("health-run", False, "%s: %s" % (type(ex).__name__, ex)))
        bad = [c.name for c in checks if not c.ok]
        have = all(self.config.lootpak.get(k) for k in ("ncstool", "bl4", "uextract"))
        summary = ("%d self-checks passed; tools %s" % (len(checks), "configured" if have else "NOT configured "
                   "([lootpak] in config.toml)")) if not bad else "failed: " + ", ".join(bad)
        return HealthReport.from_checks(checks, summary)


MODULE = LootPakModule
