"""Shared plumbing for the command line: exit codes, user-facing errors, and the Context that
commands receive. Contains no domain logic and touches modules only through the Forge.

DISCLOSURE (what this code does)
  Reads: config.toml (path from --config or $BL4FORGE_CONFIG). Writes: stdout/stderr only. Network: none. Risk: none.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional, Set

from ..core.config import Config
from ..core.forge import DEGRADED, Forge

# ---- exit codes (documented in `bl4forge --help`) --------------------------------------------
EXIT_OK = 0
EXIT_CHECK_FAILED = 1    # doctor reports an unhealthy module, or validate found problems
EXIT_USAGE = 2           # bad arguments, bad spec, bad serial, refused operation, bad config
EXIT_NOTHING = 3         # build: nothing in the spec resolved
EXIT_UNAVAILABLE = 4     # a needed module is failed/blocked/not implemented, or data is missing
EXIT_FAILED = 5          # any other failure (internal error)

DOCTOR_HINT = "run 'bl4forge doctor' for details"


class CliError(Exception):
    """An expected, user-facing failure: printed as one `error:` line, never as a traceback."""

    def __init__(self, message: str, code: int = EXIT_USAGE):
        super().__init__(message)
        self.message = message
        self.code = code


def out(text: str = "") -> None:
    print(text, file=sys.stdout)


def err(text: str = "") -> None:
    print(text, file=sys.stderr)


def warn(text: str) -> None:
    err("warning: %s" % text)


def note(text: str) -> None:
    err("note: %s" % text)


def emit_json(obj: Any) -> None:
    out(json.dumps(obj, indent=1))


class Context:
    """What a command gets: the Forge, the parsed arguments, and `use()` to reach one module."""

    def __init__(self, forge: Forge, args: Any):
        self.forge = forge
        self.args = args
        self._warned: Set[str] = set()

    @property
    def config(self) -> Config:
        return self.forge.config

    def use(self, name: str):
        """The module instance, or `ModuleUnavailable` (handled once, at the top level).
        A DEGRADED module is still handed back, with a one-line warning."""
        inst = self.forge.module(name)
        state = self.forge.states.get(name)
        if state is not None and state.state == DEGRADED and name not in self._warned:
            self._warned.add(name)
            warn("module '%s' is degraded (%s); results may be incomplete - %s"
                 % (name, state.detail or "no detail", DOCTOR_HINT))
        return inst


def load_config(path_arg: Optional[str]) -> Config:
    """`--config PATH` beats BL4FORGE_CONFIG beats <root>/config.toml. A path that was asked for
    explicitly but does not exist is an error: silently falling back to the default ownership
    settings would be worse than refusing."""
    explicit = path_arg or os.environ.get("BL4FORGE_CONFIG")
    if explicit:
        path = Path(os.path.expanduser(explicit))
        if not path.is_file():
            source = "--config" if path_arg else "BL4FORGE_CONFIG"
            raise CliError("%s: no such config file: %s" % (source, explicit), EXIT_USAGE)
        return Config.load(path=path)
    return Config.load()
