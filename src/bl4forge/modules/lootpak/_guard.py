"""Write protection for the loot-pak builder. A build writes ONLY into a brand-new output folder.

Refused: the base's folder (or anything inside it, or a folder that contains it), an out folder that already
exists (an `outN` name, or any non-empty folder), and anything under a folder named `backups`.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

from ...core.errors import LootPakError

_OUTN = re.compile(r"^out\d+[a-z]*$", re.IGNORECASE)


def _resolve(p: Path) -> Path:
    try:
        return Path(p).resolve()
    except OSError:
        return Path(p).absolute()


def _is_within(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def under_backups(p: Path) -> bool:
    parts = [x.lower() for x in _resolve(p).parts]
    return "backups" in parts[:-1] or (bool(parts) and parts[-1] == "backups")


def check_out_dir(out_dir: Path, inputs: Iterable[Path], protected: Sequence[Path] = ()) -> Path:
    """Return the resolved output folder, or raise LootPakError saying why it is refused."""
    out = _resolve(out_dir)
    if under_backups(out):
        raise LootPakError("refusing to write under a 'backups' folder: %s" % out)
    guarded = [_resolve(Path(p)) for p in protected]
    for f in inputs:
        fr = _resolve(Path(f))
        guarded.append(fr.parent)
        guarded.append(fr)
    for g in guarded:
        if _is_within(out, g) or _is_within(g, out):
            raise LootPakError("refusing to write into or around the base input %s (output %s)" % (g, out))
    if out.exists():
        if not out.is_dir():
            raise LootPakError("output path exists and is not a folder: %s" % out)
        if _OUTN.match(out.name) or any(out.iterdir()):
            raise LootPakError("refusing to reuse an existing output folder: %s (pick a new name)" % out)
    return out


def ensure_inside(out: Path, target: Path) -> Path:
    """Every file the builder writes goes through here: it must lie inside the output folder."""
    t = _resolve(target)
    if not _is_within(t, _resolve(out)):
        raise LootPakError("internal guard: %s is outside the output folder %s" % (t, out))
    return t
