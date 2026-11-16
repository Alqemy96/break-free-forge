"""Configuration: one immutable object, built once, handed to every module through its context."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - 3.10 fallback (declared in pyproject)
    import tomli as _toml  # type: ignore

from .errors import ConfigError

DEFAULT_OWNED_PACKS: Tuple[str, ...] = (
    "coregame", "bounty_pack_1", "bounty_pack_2", "bounty_pack_3", "bounty_pack_4", "bounty_pack_5",
)


@dataclass(frozen=True)
class Config:
    root: Path
    data_dir: Path
    level: int = 60
    character: str = "gravitar"
    owned_packs: Tuple[str, ...] = DEFAULT_OWNED_PACKS
    # Save-file keys live in config.toml ([save]), never in source. repr=False keeps them out of logs.
    save_ps5_key: Optional[bytes] = field(default=None, repr=False)
    save_pc_base_key: Optional[bytes] = field(default=None, repr=False)
    # [lootpak]: paths of the external build tools (ncstool, bl4, uextract) and the modwork folder.
    lootpak: Dict[str, str] = field(default_factory=dict)

    @property
    def manifest_dir(self) -> Path:
        return self.data_dir / "manifest"

    @property
    def serial_db_path(self) -> Path:
        return self.data_dir / "bl4-serial-matches.json"

    @classmethod
    def default(cls, root: Optional[os.PathLike] = None) -> "Config":
        return cls.load(root=root, path=None, _read_file=False)

    @classmethod
    def load(cls, path: Optional[os.PathLike] = None, root: Optional[os.PathLike] = None,
             _read_file: bool = True) -> "Config":
        root_path = Path(root) if root else _find_root()
        cfg_path = Path(path) if path else Path(os.environ.get("BL4FORGE_CONFIG", root_path / "config.toml"))
        raw: dict = {}
        if _read_file and cfg_path.is_file():
            try:
                raw = _toml.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception as ex:  # tomllib raises TOMLDecodeError; keep one error type outward
                raise ConfigError("cannot read %s: %s" % (cfg_path, ex)) from ex
        forge = raw.get("forge", {})
        own = raw.get("ownership", {})
        data_dir = Path(forge.get("data_dir", "data"))
        if not data_dir.is_absolute():
            data_dir = root_path / data_dir
        level = forge.get("level", 60)
        if not isinstance(level, int) or not (1 <= level <= 100):
            raise ConfigError("forge.level must be an integer 1-100, got %r" % (level,))
        packs = own.get("packs", list(DEFAULT_OWNED_PACKS))
        if not isinstance(packs, list) or not all(isinstance(p, str) for p in packs):
            raise ConfigError("ownership.packs must be a list of strings")
        save = raw.get("save", {})
        if not isinstance(save, dict):
            raise ConfigError("[save] must be a table")
        lootpak = raw.get("lootpak", {})
        if not isinstance(lootpak, dict) or not all(isinstance(v, str) for v in lootpak.values()):
            raise ConfigError("[lootpak] must be a table of path strings")
        return cls(root=root_path, data_dir=data_dir, level=level,
                   character=str(forge.get("character", "gravitar")), owned_packs=tuple(packs),
                   save_ps5_key=_hex_key(save, "ps5_key"), save_pc_base_key=_hex_key(save, "pc_base_key"), lootpak=dict(lootpak))


def _hex_key(table: dict, name: str) -> Optional[bytes]:
    """`[save] <name>` as 32 bytes from 64 hex digits (spaces allowed), or None when absent/blank."""
    raw = table.get(name)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if not isinstance(raw, str):
        raise ConfigError("save.%s must be a string of 64 hex digits" % name)
    text = "".join(raw.split())
    try:
        key = bytes.fromhex(text)
    except ValueError:
        raise ConfigError("save.%s must be hex digits only" % name) from None
    if len(key) != 32:
        raise ConfigError("save.%s must be 32 bytes (64 hex digits), got %d bytes" % (name, len(key)))
    return key


def _find_root() -> Path:
    env = os.environ.get("BL4FORGE_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:           # src/bl4forge/core/config.py -> project root
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "bl4forge").is_dir():
            return parent
    return Path.cwd()
