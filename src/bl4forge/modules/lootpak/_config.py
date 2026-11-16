"""The loot-pak build config (TOML): syntax-level parsing and validation. No tools, no game files.

Rows and fields are NAMED here, never addressed by bit position. Which table a section edits, which fields it
may touch, and the allowed numeric range of each field is the `SECTIONS` whitelist below.

    [meta]            name, notes
    [base]            raw (base raw table), inventory (base inventory ncs), reference_pak (e.g. out3's pak)
                      relative paths resolve against [lootpak] modwork in config.toml (else the config's folder)
    [pak]             name, mount, seed            (defaults = the hand recipes: see PAK_DEFAULTS)
    [enemydrops.<Rank>]        guns_probability, classmods_probability, ..., exp_multiplier,
                               rarity_modifier.commonmodifier, ...
    [rarity_balance.<Tier>]    base_weight
    [difficulty_standard.<Row>] / [difficulty_uvh.<Row>]   lootluck
    [lootablebalance.<Row>]    commonmodifier ... pearlmodifier (only the ones the row already has)
    [spawnbalance.<Row>]       oneplayer_constant (Table_PlayerCountSpawnBalanceData, solo play only; every
                               other field, and the twoplayers/threeplayers/fourplayers columns, is refused).
                               Row names with '+' or '&' need quotes: [spawnbalance."2P+_add1"]
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - 3.10 fallback (declared in pyproject)
    import tomli as _toml  # type: ignore

from ...core.errors import ConfigError

PAK_DEFAULTS = {"name": "pakchunk100-ps5_P.pak", "mount": "../../../", "seed": 2190688979}
NCS_DIR = "Engine/Content/_NCS"
TABLE0_NCS = "Nexus-Data-gbx_ue_data_table0.ncs"
INVENTORY_NCS = "Nexus-Data-inventory_container0.ncs"

_PROB = (0.0, 1.0)
_MOD = (0.0, 1000.0)
_ENEMY_FIELDS: Dict[str, Tuple[float, float]] = {
    "classmods_probability": _PROB, "enhancements_probability": _PROB, "repkits_probability": _PROB,
    "grenadesorgadgets_probability": _PROB, "shields_probability": _PROB, "guns_probability": _PROB,
    "exp_multiplier": (0.0, 100.0),
}
_MODIFIERS = ("commonmodifier", "uncommonmodifier", "raremodifier", "veryraremodifier", "legendarymodifier",
              "pearlmodifier")
for _m in _MODIFIERS:
    _ENEMY_FIELDS["rarity_modifier." + _m] = _MOD

# section name -> (decode table key, {field path -> (min, max)})
SECTIONS: Dict[str, Tuple[str, Dict[str, Tuple[float, float]]]] = {
    "enemydrops": ("table_enemydrops", _ENEMY_FIELDS),
    "rarity_balance": ("rarity_balance", {"base_weight": (0.0, 1000.0)}),
    "difficulty_standard": ("table_difficulty_standard", {"lootluck": (0.0, 1000.0)}),
    "difficulty_uvh": ("table_difficulty_uvh", {"lootluck": (0.0, 1000.0)}),
    "lootablebalance": ("table_lootablebalance", {m: _MOD for m in _MODIFIERS}),
    # solo-play enemy count only: the co-op columns must stay untouched, so they are not in the whitelist
    "spawnbalance": ("table_playercountspawnbalancedata", {"oneplayer.constant": (0.0, 20.0)}),
}
# config spelling -> decode path (the nested spelling [spawnbalance.Row.oneplayer] constant = 2 is also accepted)
FIELD_ALIASES: Dict[str, Dict[str, str]] = {"spawnbalance": {"oneplayer_constant": "oneplayer.constant"}}


@dataclass(frozen=True)
class BaseSpec:
    raw: Path
    inventory: Path
    reference_pak: Path
    raw_sha256: Optional[str] = None
    inventory_sha256: Optional[str] = None
    reference_pak_sha256: Optional[str] = None


@dataclass(frozen=True)
class PakSpec:
    name: str = PAK_DEFAULTS["name"]
    mount: str = PAK_DEFAULTS["mount"]
    seed: Optional[int] = PAK_DEFAULTS["seed"]


@dataclass(frozen=True)
class Setting:
    section: str
    row: str            # as written in the config (matched case-insensitively against the base)
    field: str          # dotted field path
    value: float

    @property
    def label(self) -> str:
        return "%s.%s.%s" % (self.section, self.row, self.field)


@dataclass(frozen=True)
class LootConfig:
    name: str
    notes: str
    base: BaseSpec
    pak: PakSpec
    settings: Tuple[Setting, ...]
    source: Optional[Path] = None


def format_value(value: float) -> str:
    """The way the NCS pool spells a number: six decimals ('0.600000'). More precision is refused."""
    text = "%.6f" % value
    if abs(float(text) - value) > 1e-12:
        raise ConfigError("value %r needs more than 6 decimals; the NCS pool stores numbers as '%%.6f'" % (value,))
    return text


def _sha(table: Mapping, key: str, where: str) -> Optional[str]:
    v = table.get(key)
    if v is None or v == "":
        return None
    if not isinstance(v, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", v):
        raise ConfigError("%s.%s must be 64 hex digits" % (where, key))
    return v.lower()


def _path(table: Mapping, key: str, anchor: Path) -> Path:
    v = table.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ConfigError("[base] %s is required (a path to a file)" % key)
    p = Path(os.path.expanduser(v))
    if not p.is_absolute():
        p = anchor / p
    return p


def parse_config(text: str, source: Optional[Path] = None, modwork: Optional[Path] = None) -> LootConfig:
    """Parse and validate the TOML text. Raises ConfigError naming the section/row/field at fault."""
    try:
        raw = _toml.loads(text)
    except Exception as ex:                      # tomllib.TOMLDecodeError (this also catches duplicate keys)
        raise ConfigError("cannot parse the loot-pak config: %s" % ex) from ex
    known = {"meta", "base", "pak"} | set(SECTIONS)
    for k in raw:
        if k not in known:
            raise ConfigError("unknown section [%s]; known: %s" % (k, ", ".join(sorted(known))))
    meta = raw.get("meta", {})
    name = str(meta.get("name", "")).strip() or "lootpak"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ConfigError("[meta] name may only use letters, digits, '_', '.', '-' (got %r)" % name)
    base_t = raw.get("base")
    if not isinstance(base_t, dict):
        raise ConfigError("[base] is required: raw, inventory, reference_pak")
    for k in base_t:
        if k not in ("raw", "inventory", "reference_pak", "raw_sha256", "inventory_sha256", "reference_pak_sha256"):
            raise ConfigError("[base] unknown key %r" % k)
    anchor = modwork if modwork is not None else (source.parent if source is not None else Path.cwd())
    base = BaseSpec(raw=_path(base_t, "raw", anchor), inventory=_path(base_t, "inventory", anchor),
                    reference_pak=_path(base_t, "reference_pak", anchor),
                    raw_sha256=_sha(base_t, "raw_sha256", "base"),
                    inventory_sha256=_sha(base_t, "inventory_sha256", "base"),
                    reference_pak_sha256=_sha(base_t, "reference_pak_sha256", "base"))
    pak_t = raw.get("pak", {})
    for k in pak_t:
        if k not in PAK_DEFAULTS:
            raise ConfigError("[pak] unknown key %r (known: name, mount, seed)" % k)
    seed = pak_t.get("seed", PAK_DEFAULTS["seed"])
    if seed in ("none", None):
        seed = None
    elif isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2 ** 64:
        raise ConfigError("[pak] seed must be an unsigned 64-bit integer or \"none\"")
    pname = pak_t.get("name", PAK_DEFAULTS["name"])
    if not isinstance(pname, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+\.pak", pname):
        raise ConfigError("[pak] name must be a plain file name ending in .pak")
    pak = PakSpec(name=pname, mount=str(pak_t.get("mount", PAK_DEFAULTS["mount"])), seed=seed)

    settings: List[Setting] = []
    seen: Dict[Tuple[str, str, str], str] = {}
    for section in sorted(set(SECTIONS) & set(raw)):
        rows = raw[section]
        if not isinstance(rows, dict) or not rows:
            raise ConfigError("[%s] must contain rows, e.g. [%s.Elite]" % (section, section))
        allowed = SECTIONS[section][1]
        for row, fields in rows.items():
            if not isinstance(fields, dict) or not fields:
                raise ConfigError("[%s.%s] must be a table of fields" % (section, row))
            for path, value in _flatten(fields, section, row):
                path = FIELD_ALIASES.get(section, {}).get(path, path)
                if path not in allowed:
                    raise ConfigError("[%s.%s] unknown field %r; allowed: %s"
                                      % (section, row, path, ", ".join(sorted(allowed))))
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ConfigError("[%s.%s] %s must be a number, got %r" % (section, row, path, value))
                value = float(value)
                lo, hi = allowed[path]
                if not math.isfinite(value) or not lo <= value <= hi:
                    raise ConfigError("[%s.%s] %s = %r is out of range (%g..%g)" % (section, row, path, value, lo, hi))
                format_value(value)                     # precision check
                key = (section, row.lower(), path)
                if key in seen:
                    raise ConfigError("duplicate setting: %s.%s.%s (rows %r and %r)"
                                      % (section, row, path, seen[key], row))
                seen[key] = row
                settings.append(Setting(section, row, path, value))
    return LootConfig(name=name, notes=str(meta.get("notes", "")), base=base, pak=pak,
                      settings=tuple(settings), source=source)


def _flatten(table: Mapping, section: str, row: str, prefix: str = ""):
    for k, v in table.items():
        path = prefix + k
        if isinstance(v, dict):
            if not v:
                raise ConfigError("[%s.%s] %s is an empty table" % (section, row, path))
            yield from _flatten(v, section, row, path + ".")
        else:
            yield path, v


def load_config_file(path: os.PathLike, modwork: Optional[Path] = None) -> LootConfig:
    p = Path(path)
    if not p.is_file():
        raise ConfigError("no such loot-pak config: %s" % p)
    return parse_config(p.read_text(encoding="utf-8"), source=p, modwork=modwork)
