"""codec: Turn '@U...' serials into bitstream blocks and back, bit-exactly.

Pure, stateless, file-free. All wire-format work lives in `_wire.py`; this file is the cell: the
`CodecPort` methods, the item semantics layered on the blocks (category id, level, seed positions),
and the known-answer `health()`. Read CONTRACT.md in this directory for the rules and deviations.


DISCLOSURE (what this code does)
  Reads: nothing from disk. Writes: nothing. Network: none. Risk: none (pure computation on values passed in).
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from ...core.errors import SerialError
from ...core.module import Module
from ...core.ports import CodecPort
from ...core.types import (
    Block, Blocks, HealthCheck, HealthReport, TOK_VARBIT, TOK_VARINT,
)
from . import _wire
from ._known import KNOWN_SERIALS

_INT_TOKENS = (TOK_VARINT, TOK_VARBIT)
_SEED_POSITION = 5          # the stat-variance seed is the 6th integer block (legacy SEED_INT_POS)
_HEALTH_PROBE_SEED = 1234
_HEALTH_PROBE_LEVEL = 60


def _int_indices(blocks: object) -> Tuple[int, ...]:
    """Indices (into `blocks`) of the plain integer blocks, in order. Validates the argument."""
    if not isinstance(blocks, (tuple, list)):
        raise SerialError("expected Blocks (a tuple of Block), got %s" % type(blocks).__name__)
    idx = []
    for i, b in enumerate(blocks):
        if not isinstance(b, Block):
            raise SerialError("blocks[%d] is not a Block (got %s)" % (i, type(b).__name__))
        if b.token in _INT_TOKENS:
            idx.append(i)
    return tuple(idx)


def _position(position: object) -> int:
    if not _wire.is_int(position):
        raise SerialError("position must be an integer, got %s" % _wire.show(position))
    return position  # type: ignore[return-value]


def _level_index(blocks: object) -> Optional[int]:
    """Index of the block holding the item level, or None.

    Header, read as integer blocks: [category, 0, 1 (marker), LEVEL, 2, seed, ...]. Starting at
    integer position 2 and stepping by 2, the first marker value 1 is followed by the level.
    """
    ints = _int_indices(blocks)
    pos = 2
    while pos < len(ints):
        if blocks[ints[pos]].value == 1:  # type: ignore[index]
            return ints[pos + 1] if pos + 1 < len(ints) else None
        pos += 2
    return None


class CodecModule(Module):
    name = "codec"
    purpose = "Turn '@U...' serials into bitstream blocks and back, bit-exactly."
    requires = ()
    port = CodecPort

    # Largest value an integer block (and an item level or seed) can carry. Part-list values share it;
    # part indexes and plain integer-part values are limited to MAX_PART_VALUE.
    MAX_INT_VALUE = _wire.MAX_VARBIT
    MAX_PART_VALUE = _wire.MAX_VARINT

    # ---- wire format -------------------------------------------------------------------------
    def decode(self, serial: str) -> Blocks:
        return _wire.decode_blocks(serial)

    def encode(self, blocks: Blocks) -> str:
        return _wire.encode_blocks(blocks)

    def parts_string(self, blocks: Blocks) -> str:
        return _wire.parts_string(blocks)

    def from_string(self, text: str) -> Blocks:
        return _wire.from_string(text)

    # ---- item semantics ----------------------------------------------------------------------
    def get_level(self, blocks: Blocks) -> Optional[int]:
        idx = _level_index(blocks)
        return None if idx is None else blocks[idx].value

    def get_category_id(self, blocks: Blocks) -> Optional[int]:
        return self.int_at(blocks, 0)

    def relevel(self, serial: str, level: int) -> str:
        blocks = self.decode(serial)
        idx = _level_index(blocks)
        if idx is None:
            raise SerialError("could not locate the level in this serial")
        new = _wire.int_block(level, "level")
        return self.encode(blocks[:idx] + (new,) + blocks[idx + 1:])

    def int_at(self, blocks: Blocks, position: int) -> Optional[int]:
        pos = _position(position)
        ints = _int_indices(blocks)
        if pos < 0 or pos >= len(ints):
            return None
        return blocks[ints[pos]].value

    def with_int_at(self, blocks: Blocks, position: int, value: int) -> Blocks:
        pos = _position(position)
        ints = _int_indices(blocks)
        if pos < 0 or pos >= len(ints):
            raise SerialError("no integer block at position %s (this serial has %d)" % (_wire.show(pos), len(ints)))
        new = _wire.int_block(value, "value")
        at = ints[pos]
        return tuple(blocks[:at]) + (new,) + tuple(blocks[at + 1:])

    # ---- self-check --------------------------------------------------------------------------
    def health(self) -> HealthReport:
        checks: List[HealthCheck] = []
        try:
            for label, serial, level, category, seed, text in KNOWN_SERIALS:
                checks.append(self._check_known(label, serial, level, category, seed, text))
            checks.append(self._check_errors())
            checks.append(self._check_immutable())
        except Exception as ex:  # health() must never raise
            checks.append(HealthCheck("health-run", False, "%s: %s" % (type(ex).__name__, ex)))
        bad = [c.name for c in checks if not c.ok]
        summary = ("%d known-answer checks passed" % len(checks)) if not bad else \
            "failed: " + ", ".join(bad)
        return HealthReport.from_checks(checks, summary)

    def _check_known(self, label: str, serial: str, level: int, category: int, seed: int,
                     text: str) -> HealthCheck:
        name = "known-answer: " + label
        try:
            blocks = self.decode(serial)
            got = (self.get_level(blocks), self.get_category_id(blocks), self.int_at(blocks, _SEED_POSITION))
            if got != (level, category, seed):
                return HealthCheck(name, False, "level/category/seed %r, expected %r" % (got, (level, category, seed)))
            if self.parts_string(blocks) != text:
                return HealthCheck(name, False, "parts_string differs from the known answer")
            if self.encode(blocks) != serial:
                return HealthCheck(name, False, "encode(decode(s)) != s")
            if self.encode(self.from_string(text)) != serial:
                return HealthCheck(name, False, "encode(from_string(parts_string)) != s")
            up = self.relevel(serial, _HEALTH_PROBE_LEVEL)
            up_blocks = self.decode(up)
            if (self.get_level(up_blocks), self.get_category_id(up_blocks)) != (_HEALTH_PROBE_LEVEL, category):
                return HealthCheck(name, False, "relevel to %d did not take" % _HEALTH_PROBE_LEVEL)
            if self.relevel(up, level) != serial:
                return HealthCheck(name, False, "relevel back to %d did not restore the serial" % level)
            reseeded = self.with_int_at(blocks, _SEED_POSITION, _HEALTH_PROBE_SEED)
            if self.int_at(reseeded, _SEED_POSITION) != _HEALTH_PROBE_SEED or \
                    self.with_int_at(reseeded, _SEED_POSITION, seed) != blocks:
                return HealthCheck(name, False, "seed replace/restore failed")
        except Exception as ex:
            return HealthCheck(name, False, "%s: %s" % (type(ex).__name__, ex))
        return HealthCheck(name, True, "level %d, category %d" % (level, category))

    def _check_errors(self) -> HealthCheck:
        for bad in ("", "@U", "not a serial", KNOWN_SERIALS[0][1][:-3]):
            try:
                self.decode(bad)
            except SerialError:
                continue
            except Exception as ex:
                return HealthCheck("errors-are-serialerror", False, "%r raised %s" % (bad, type(ex).__name__))
            return HealthCheck("errors-are-serialerror", False, "%r was accepted" % bad)
        return HealthCheck("errors-are-serialerror", True, "garbage and truncated input raise SerialError")

    def _check_immutable(self) -> HealthCheck:
        blocks = self.decode(KNOWN_SERIALS[0][1])
        before = tuple(blocks)
        self.relevel(KNOWN_SERIALS[0][1], _HEALTH_PROBE_LEVEL)
        self.with_int_at(blocks, _SEED_POSITION, _HEALTH_PROBE_SEED)
        if blocks != before:
            return HealthCheck("immutable", False, "an input was modified")
        try:
            blocks[0].value = 7  # type: ignore[misc]
        except Exception:
            return HealthCheck("immutable", True, "blocks are frozen and inputs untouched")
        return HealthCheck("immutable", False, "Block is not frozen")


MODULE = CodecModule
