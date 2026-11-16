"""Command line (outer layer). Uses a Forge; contains no domain logic.

Entry point: `bl4forge.cli:main(argv=None, forge=None) -> int` (also `python -m bl4forge`).
`forge` lets tests (and the future web layer) hand in a ready Forge; otherwise main() builds one,
starting only the modules the chosen command needs.

Importing this package does no work; everything happens inside main().


DISCLOSURE (what this code does)
  Reads: config.toml (or the file named by --config / $BL4FORGE_CONFIG) and whatever files the chosen command names. Writes: only what the chosen command writes (see DISCLOSURE.md). Network: none here; only `serve` opens a local listening port (loopback by default). Risk: see the table in DISCLOSURE.md; every command that edits a save writes a COPY and never the original.
"""
from __future__ import annotations

import os
import sys
import traceback
from typing import List, Optional

from ..core.errors import (ConfigError, DataMissing, ForgeError, LootPakError, ModuleUnavailable,
                           SaveError, SerialError)
from ..core.forge import Forge
from ._core import (CliError, Context, DOCTOR_HINT, EXIT_FAILED, EXIT_OK, EXIT_UNAVAILABLE, EXIT_USAGE,
                    err, load_config)
from ._parser import build_parser

__all__ = ["main"]


def _harden_streams() -> None:
    """A Windows pipe/console may not be UTF-8; part names contain characters like an em dash.
    Never let output encoding turn a successful command into a crash."""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", None) or "").lower().replace("-", "").replace("_", "")
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None and enc not in ("utf8", "utf8sig"):
            try:
                reconfigure(errors="replace")
            except Exception:
                pass


def _exit_code(code) -> int:
    if code is None:
        return EXIT_OK
    return code if isinstance(code, int) else EXIT_USAGE


def _start_forge(args) -> Forge:
    config = load_config(getattr(args, "config_path", None))
    needs = getattr(args, "needs", None)
    return Forge.build(config, only=list(needs) if needs else None)


def _report(ex: BaseException, debug: bool) -> int:
    """Turn an exception into one `error:` line (plus a traceback under --debug) and an exit code."""
    if isinstance(ex, CliError):
        msg, code = ex.message, ex.code
    elif isinstance(ex, ModuleUnavailable):
        msg, code = "%s (%s)" % (ex, DOCTOR_HINT), EXIT_UNAVAILABLE
    elif isinstance(ex, DataMissing):
        msg, code = ("required data is missing: %s (%s). This public copy ships NO game data: you must supply your "
                     "own serial database and manifest under data_dir (see docs/runbooks/DEVELOPER.md, 'Supplying "
                     "data'). Serial decode/encode and save editing work without it." % (ex, DOCTOR_HINT)), EXIT_UNAVAILABLE
    elif isinstance(ex, NotImplementedError):
        msg, code = "%s (%s)" % (ex, DOCTOR_HINT), EXIT_UNAVAILABLE
    elif isinstance(ex, ConfigError):
        msg, code = "config error: %s" % ex, EXIT_USAGE
    elif isinstance(ex, (SerialError, SaveError, LootPakError)):    # SaveKeyMissing is a SaveError: fix config, retry
        msg, code = str(ex), EXIT_USAGE
    elif isinstance(ex, ForgeError):
        msg, code = str(ex), EXIT_FAILED
    else:
        msg, code = "internal error: %s: %s (re-run with --debug for the traceback)" % (
            type(ex).__name__, ex), EXIT_FAILED
    err("error: %s" % msg)
    if debug:
        err("".join(traceback.format_exception(type(ex), ex, ex.__traceback__)).rstrip())
    return code


def main(argv: Optional[List[str]] = None, forge: Optional[Forge] = None) -> int:
    _harden_streams()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as ex:           # argparse: --help (0) or a usage error (2)
        return _exit_code(ex.code)
    debug = bool(getattr(args, "debug", False))
    try:
        if forge is None:
            forge = _start_forge(args)
        return int(args.func(Context(forge, args), args) or 0)
    except BrokenPipeError:            # e.g. `bl4forge catalog | head`
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except Exception:
            pass
        return EXIT_OK
    except KeyboardInterrupt:
        err("interrupted")
        return 130
    except Exception as ex:            # expected failures are ForgeError/CliError; anything else is a bug
        return _report(ex, debug)


if __name__ == "__main__":
    sys.exit(main())
