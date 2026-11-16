"""The subprocess adapter: the ONLY place the loot-pak cell runs an external program.

`Tools` is the interface the planner and builder use; tests hand in a fake. `SubprocessTools` runs the external
Rust tools (ncstool, bl4, uextract) exactly as the hand recipes in a hand-run REGEN.txt did. It touches no
console and no network: it only reads and writes local files whose paths it is given.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from ...core.errors import LootPakError

Triple = Tuple[int, int, int, int]            # bitpos, bits, old index, new index
Entry = Tuple[str, Path]                      # pak member name, file


class Tools:
    """Interface. Every method takes and returns plain paths/text so a fake can be swapped in."""

    def leaves(self, raw: Path) -> str:                                   # NCS_LEAFLOG=1 ncstool leaves
        raise NotImplementedError

    def strings(self, raw: Path) -> str:                                  # ncstool strings
        raise NotImplementedError

    def set_bits(self, src: Path, dst: Path, binoff: int, triples: Sequence[Triple]) -> str:
        raise NotImplementedError

    def wrap(self, raw: Path, ncs: Path) -> None:                         # ncstool wrap
        raise NotImplementedError

    def decode(self, ncs: Path) -> str:                                   # bl4 ncs show
        raise NotImplementedError

    def mkpak(self, out: Path, mount: str, seed: Optional[int], reference_pak: Path,
              entries: Sequence[Entry]) -> None:                          # ncstool mkpak
        raise NotImplementedError

    def extract(self, pak: Path, out_dir: Path) -> List[Path]:            # uextract pak -o
        raise NotImplementedError

    def fingerprints(self) -> Dict[str, str]:                             # tool name -> sha256 (for the manifest)
        return {}

    def commands(self) -> Mapping[str, str]:                              # tool name -> path (for REGEN.txt)
        return {}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class SubprocessTools(Tools):
    def __init__(self, ncstool: Path, bl4: Path, uextract: Path, timeout: float = 300.0):
        self.ncstool, self.bl4, self.uextract = Path(ncstool), Path(bl4), Path(uextract)
        self.timeout = timeout

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> "SubprocessTools":
        """From the `[lootpak]` table of config.toml: ncstool, bl4, uextract (full paths)."""
        missing = [k for k in ("ncstool", "bl4", "uextract") if not settings.get(k)]
        if missing:
            raise LootPakError("config.toml [lootpak] is missing %s (full path of each tool; see "
                               "config.example.toml)" % ", ".join(missing))
        tools = cls(Path(settings["ncstool"]), Path(settings["bl4"]), Path(settings["uextract"]))
        absent = [str(p) for p in (tools.ncstool, tools.bl4, tools.uextract) if not p.is_file()]
        if absent:
            raise LootPakError("tool not found: %s" % ", ".join(absent))
        return tools

    # ---- plumbing ----
    def _run(self, args: Sequence[object], env_extra: Optional[Mapping[str, str]] = None):
        argv = [str(a) for a in args]
        env = dict(os.environ)
        env.update(env_extra or {})
        try:
            cp = subprocess.run(argv, capture_output=True, env=env, timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired) as ex:
            raise LootPakError("could not run %s: %s" % (Path(argv[0]).name, ex)) from ex
        if cp.returncode != 0:
            raise LootPakError("%s %s failed (exit %d): %s" % (
                Path(argv[0]).name, argv[1] if len(argv) > 1 else "", cp.returncode,
                cp.stderr.decode("utf-8", "replace").strip()[-600:]))
        return cp

    @staticmethod
    def _text(data: bytes) -> str:
        return data.decode("utf-8", "replace").replace("\r\n", "\n")

    # ---- operations (argument order exactly as in the REGEN recipes) ----
    def leaves(self, raw: Path) -> str:
        return self._text(self._run([self.ncstool, "leaves", raw], {"NCS_LEAFLOG": "1"}).stderr)

    def strings(self, raw: Path) -> str:
        return self._text(self._run([self.ncstool, "strings", raw]).stdout)

    def set_bits(self, src: Path, dst: Path, binoff: int, triples: Sequence[Triple]) -> str:
        args: List[object] = [self.ncstool, "set-bits", src, dst, binoff]
        for t in triples:
            args.extend(t)
        return self._text(self._run(args).stdout)

    def wrap(self, raw: Path, ncs: Path) -> None:
        self._run([self.ncstool, "wrap", raw, ncs])

    def decode(self, ncs: Path) -> str:
        return self._text(self._run([self.bl4, "ncs", "show", ncs]).stdout)

    def mkpak(self, out: Path, mount: str, seed: Optional[int], reference_pak: Path,
              entries: Sequence[Entry]) -> None:
        args: List[object] = [self.ncstool, "mkpak", out, mount, "none" if seed is None else seed, reference_pak]
        args.extend("%s=%s" % (name, path) for name, path in entries)
        self._run(args)

    def extract(self, pak: Path, out_dir: Path) -> List[Path]:
        self._run([self.uextract, "pak", pak, "-o", out_dir])
        return sorted(p for p in Path(out_dir).rglob("*") if p.is_file())

    def fingerprints(self) -> Dict[str, str]:
        return {"ncstool": file_sha256(self.ncstool), "bl4": file_sha256(self.bl4),
                "uextract": file_sha256(self.uextract)}

    def commands(self) -> Mapping[str, str]:
        return {"ncstool": str(self.ncstool), "bl4": str(self.bl4), "uextract": str(self.uextract)}
