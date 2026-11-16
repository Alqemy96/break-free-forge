"""Test doubles: legacy-backed stand-ins for modules that are not built yet (or are under test).

A module under development gets its REAL leaf neighbours (codec, data) and a double for any
neighbour that is still being built in parallel. Doubles implement the same Port, so a module that
only touches its declared neighbours through ports cannot tell the difference. When the real
neighbour lands, delete the override and re-run: the same tests must still pass.

Usage in a test:
    from tests.doubles import build_forge          # (tests/ is on sys.path via conftest)
    forge = build_forge(config, legacy, doubles=("rules",))        # real codec/data, legacy rules
    ops = forge.ops
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from bl4forge.core import vocab
from bl4forge.core.errors import SerialError
from bl4forge.core.forge import Forge
from bl4forge.core.module import Module, ModuleContext
from bl4forge.core.types import HealthReport, ItemInfo, PartRef


def _wrap(fn, *a, **k):
    try:
        return fn(*a, **k)
    except SerialError:
        raise
    except Exception as ex:  # legacy raises ValueError/IndexError; the port says SerialError
        raise SerialError(str(ex)) from ex


def _element(label: Optional[str]) -> Optional[str]:
    return vocab.normalize_element(label) if label else None


class LegacyRules:
    """RulesPort backed by the legacy scripts. Behaviour = the oracle, by construction."""
    name = "rules"

    def __init__(self, legacy, config):
        self._L = legacy
        legacy.partsdb.set_owned_packs(config.owned_packs)

    def owned_packs(self) -> FrozenSet[str]:
        return frozenset(self._L.partsdb.owned_packs())

    def pack_label(self, pack: str) -> str:
        return self._L.partsdb.CONTENT_PACKS.get(pack, pack)

    def pack_of(self, category_id: Optional[int], index: int) -> str:
        return self._L.partsdb.pack_of(category_id, index)

    def is_owned(self, category_id: Optional[int], index: int) -> bool:
        return self._L.partsdb.is_owned(category_id, index)

    def serial_ownership(self, serial: str) -> Tuple[bool, Optional[str]]:
        info = self._L.partsdb.describe(serial)
        owned = info.get("owned", True)
        return owned, (None if owned else info.get("content_pack"))

    def validate(self, serial: str) -> List[str]:
        return _wrap(self._L.partsdb.validate, serial)

    def health(self) -> HealthReport:
        return HealthReport(ok=True, summary="legacy double")


class LegacyOps:
    """OpsPort backed by the legacy scripts. `describe` converts the legacy dict to ItemInfo."""
    name = "ops"

    def __init__(self, legacy, config):
        self._L = legacy
        legacy.partsdb.set_owned_packs(config.owned_packs)

    def describe(self, serial: str) -> ItemInfo:
        d = _wrap(self._L.partsdb.describe, serial)
        return ItemInfo(
            serial=serial, category_id=d["category_id"], category=d["category"], level=d["level"],
            rarity=d["rarity"], element=_element(d["element"]), legendary_name=d["legendary_name"],
            display_name=d["display_name"], parts=tuple(self._ref(p) for p in d["parts"]),
            other_components=tuple((c["rarity"], c["name"]) for c in d.get("other_components", [])),
            tokens=d["tokens"], content_pack=d.get("content_pack", "coregame"),
            content_pack_label=d.get("content_pack_label", "Base game"), owned=d.get("owned", True),
            manifest_ok=d["manifest"], warnings=tuple(d["warnings"]))

    @staticmethod
    def _ref(p) -> PartRef:
        return PartRef(token_index=p.token_index, category_id=p.category_id, index=p.index,
                       raw=p.raw, name=p.name, category_link=p.category_link)

    def rarity_estimate(self, info: ItemInfo) -> Mapping[str, object]:
        return self._L.partsdb.rarity_estimate(self._L.partsdb.describe(info.serial))

    def format_odds(self, estimate: Mapping[str, object]) -> str:
        return self._L.partsdb.format_odds(dict(estimate))

    def part_list(self, serial: str) -> List[PartRef]:
        return [self._ref(p) for p in _wrap(self._L.partsdb.part_list, serial)]

    def set_element(self, serial: str, element: Optional[str]) -> str:
        return _wrap(self._L.partsdb.set_element, serial, element)

    def get_seed(self, serial: str) -> Optional[int]:
        return _wrap(self._L.partsdb.get_seed, serial)

    def set_seed(self, serial: str, seed: int) -> str:
        return _wrap(self._L.partsdb.set_seed, serial, seed)

    def relevel(self, serial: str, level: int) -> str:
        return _wrap(self._L.codec.relevel, serial, level)

    def swap_parts(self, base: str, source: str, positions: Sequence[int],
                   allow_cross: bool = False) -> str:
        return _wrap(self._L.partsdb.swap_parts, base, source, list(positions), allow_cross)

    def diff(self, serial_a: str, serial_b: str) -> List[dict]:
        return _wrap(self._L.partsdb.diff, serial_a, serial_b)

    def health(self) -> HealthReport:
        return HealthReport(ok=True, summary="legacy double")


DOUBLES = {"rules": LegacyRules, "ops": LegacyOps}


def build_forge(config, legacy, doubles: Sequence[str] = (), only: Optional[Sequence[str]] = None) -> Forge:
    """A Forge whose real modules are used everywhere except the named `doubles`."""
    overrides = {n: DOUBLES[n](legacy, config) for n in doubles}
    return Forge.build(config, overrides=overrides, only=only)
