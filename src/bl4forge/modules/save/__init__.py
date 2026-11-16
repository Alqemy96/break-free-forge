"""save: open and re-wrap Borderlands 4 save files (PS5 and PC) and patch their YAML as text.

A leaf cell: it needs no neighbour. The crypto lives in `_aes.py` / `_container.py`, the line-level
editor in `_yamltext.py`; this file is the cell (the `SavePort` methods, key lookup from config, the
copy-only file writer, and `health()`). Read CONTRACT.md in this directory for the rules.


DISCLOSURE (what this code does)
  Reads: the save file given to write_copy (hashed before and after). Writes: ONLY an edited COPY at a destination that is not the source, plus a '<dest>.bl4forge.json' sidecar with the original's sha256; an existing destination is refused unless overwrite is set. The original is never opened for writing. Network: none. Risk: an edited save can corrupt a character; keep the original and close the game before replacing a save. The AES key is read from config.toml only and is never printed.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Dict, List, Optional, Tuple

from ...core.errors import SaveError, SaveKeyMissing
from ...core.module import Module
from ...core.ports import SavePort
from ...core.types import HealthCheck, HealthReport, SaveItem
from . import _aes, _container, _yamltext

_HEALTH_KEY = bytes(range(32))                 # a throwaway key for the self-check, NOT a game key
_HEALTH_PC_BASE = bytes(range(32, 64))
_HEALTH_YAML = (
    "state: \n"
    "  char_name: Test\n"
    "  experience: \n"
    "  - type: character\n"
    "    level: 5\n"
    "    points: 100\n"
    "  inventory: \n"
    "    items: \n"
    "      backpack: \n"
    "        slot_0: \n"
    "          serial: '@Ugabc'\n"
    "  currencies: \n"
    "    cash: 10\n"
)
SIDECAR_SUFFIX = ".bl4forge.json"


def _utf8(data: bytes, what: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as ex:
        raise SaveError("%s: decrypted data is not UTF-8 text (%s)" % (what, ex)) from None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SaveModule(Module):
    name = "save"
    purpose = "Open and re-wrap PS5/PC save files and patch their YAML as text, one line at a time."
    requires = ()
    port = SavePort

    # ---- keys (from config only) -------------------------------------------------------------
    def _ps5_key(self) -> bytes:
        key = self.config.save_ps5_key
        if key is None:
            raise SaveKeyMissing("PS5 save key is not configured: set [save] ps5_key = \"<64 hex digits>\" "
                                 "in config.toml (see config.example.toml; you must obtain the key yourself, none is shipped)")
        return key

    def _pc_key(self, steam_id: str) -> bytes:
        base = self.config.save_pc_base_key
        if base is None:
            raise SaveKeyMissing("PC save base key is not configured: set [save] pc_base_key = "
                                 "\"<64 hex digits>\" in config.toml (see config.example.toml)")
        return _container.pc_key(base, steam_id)

    # ---- container ---------------------------------------------------------------------------
    def decrypt_ps5(self, data: bytes) -> str:
        return _utf8(_container.decrypt(data, self._ps5_key(), "ps5"), "ps5 save")

    def encrypt_ps5(self, yaml_text: str) -> bytes:
        return _container.encrypt(yaml_text.encode("utf-8"), self._ps5_key(), "ps5")

    def decrypt_pc(self, data: bytes, steam_id: str) -> str:
        return _utf8(_container.decrypt(data, self._pc_key(steam_id), "pc"), "pc save")

    def encrypt_pc(self, yaml_text: str, steam_id: str) -> bytes:
        return _container.encrypt(yaml_text.encode("utf-8"), self._pc_key(steam_id), "pc")

    # ---- text editor -------------------------------------------------------------------------
    def summary(self, yaml_text: str) -> Dict[str, object]:
        return _yamltext.summary(yaml_text)

    def list_items(self, yaml_text: str) -> List[SaveItem]:
        return _yamltext.list_items(yaml_text)

    def set_currency(self, yaml_text: str, name: str, value: int) -> str:
        return _yamltext.set_currency(yaml_text, name, value)

    def set_shared_point_pool(self, yaml_text: str, name: str, value: int) -> str:
        return _yamltext.set_shared_point_pool(yaml_text, name, value)

    def shared_pool_report(self, yaml_text: str, name: str = _yamltext.ECHO_POOL) -> Optional[Dict[str, object]]:
        return _yamltext.shared_pool_report(yaml_text, name)

    def set_progress(self, yaml_text: str, level: Optional[int] = None,
                     points: Optional[int] = None) -> str:
        return _yamltext.set_progress(yaml_text, level, points)

    def set_serial(self, yaml_text: str, ref: str, serial: str) -> str:
        return _yamltext.set_serial(yaml_text, ref, serial)

    def changed_lines(self, before: str, after: str) -> List[Tuple[int, str, str]]:
        return _yamltext.changed_lines(before, after)

    # ---- files: copy only --------------------------------------------------------------------
    def sha256(self, data: bytes) -> str:
        return _sha(data)

    def write_copy(self, source_path: str, dest_path: str, data: bytes,
                   overwrite: bool = False) -> Dict[str, object]:
        """Write `data` to `dest_path`, which must NOT be the source save. The source is hashed before
        and after (it must not change) and a `<dest>.bl4forge.json` sidecar records both hashes, so the
        original stays the way back. An existing dest is refused unless `overwrite` is true."""
        src, dst = os.path.abspath(source_path), os.path.abspath(dest_path)
        if os.path.normcase(src) == os.path.normcase(dst) or (
                os.path.exists(dst) and os.path.exists(src) and os.path.samefile(src, dst)):
            raise SaveError("refusing to write over the source save %s; give a different destination" % source_path)
        if not os.path.isfile(src):
            raise SaveError("source save not found: %s" % source_path)
        if os.path.exists(dst) and not overwrite:
            raise SaveError("destination already exists: %s (pass overwrite to replace this copy)" % dest_path)
        with open(src, "rb") as fh:
            before = _sha(fh.read())
        with open(dst, "wb") as fh:
            fh.write(data)
        with open(src, "rb") as fh:
            after = _sha(fh.read())
        if before != after:
            raise SaveError("source save changed while writing the copy (%s -> %s); stop and investigate"
                            % (before[:12], after[:12]))
        record = {"source": src, "source_sha256": before, "dest": dst, "dest_sha256": _sha(data),
                  "dest_bytes": len(data), "written": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with open(dst + SIDECAR_SUFFIX, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=1)
        return record

    # ---- self-check --------------------------------------------------------------------------
    def health(self) -> HealthReport:
        checks: List[HealthCheck] = []
        try:
            checks.append(HealthCheck("aes-256 known answer (FIPS-197)", _aes.known_answer(), ""))
            for platform in ("ps5", "pc"):
                blob = _container.encrypt(_HEALTH_YAML.encode(), _HEALTH_KEY, platform)
                back = _container.decrypt(blob, _HEALTH_KEY, platform)
                checks.append(HealthCheck("%s container round trip" % platform, back == _HEALTH_YAML.encode(), ""))
            tag = _yamltext.set_currency(_HEALTH_YAML, "cash", 99)
            one = _yamltext.changed_lines(_HEALTH_YAML, tag)
            checks.append(HealthCheck("currency patch changes one line", len(one) == 1 and one[0][0] == 13, ""))
            items = _yamltext.list_items(_HEALTH_YAML)
            checks.append(HealthCheck("serial listing", [i.ref for i in items] == ["backpack/slot_0"], ""))
        except Exception as ex:  # health() must never raise
            checks.append(HealthCheck("health-run", False, "%s: %s" % (type(ex).__name__, ex)))
        bad = [c.name for c in checks if not c.ok]
        keys = "ps5 key %s, pc base key %s" % (
            "configured" if self.config.save_ps5_key else "NOT configured",
            "configured" if self.config.save_pc_base_key else "NOT configured")
        summary = ("%d self-checks passed; %s" % (len(checks), keys)) if not bad else \
            "failed: " + ", ".join(bad)
        return HealthReport.from_checks(checks, summary)


MODULE = SaveModule
