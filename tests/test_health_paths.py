"""Health/doctor output must not leak absolute local paths (account name, folder layout)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from bl4forge.core.config import Config
from bl4forge.core.doctor import diagnose, format_report, make_scrubber
from bl4forge.core.forge import Forge

ABS = re.compile(r"[A-Za-z]:[\/]|/(?:Users|home)/")


def _no_abs(text: str) -> None:
    assert not ABS.search(text), text


def test_data_label_demo_relative_and_custom(tmp_path):
    root = tmp_path / "proj"
    (root / "data" / "synthetic").mkdir(parents=True)
    assert Config.default(root=root).data_label == "data/synthetic (demo set)"
    (root / "mydata" / "manifest").mkdir(parents=True)
    cfg = Config(root=root, data_dir=root / "mydata", data_source="config")
    assert cfg.data_label == "mydata"
    outside = Config(root=root, data_dir=tmp_path / "elsewhere", data_source="env")
    assert outside.data_label == "<custom data folder>"


def test_scrubber_replaces_known_paths(tmp_path):
    root = tmp_path / "proj"
    cfg = Config(root=root, data_dir=tmp_path / "elsewhere", data_source="env",
                 lootpak={"ncstool": str(tmp_path / "tools" / "ncs.exe")})
    scrub = make_scrubber(cfg)
    out = scrub("a %s b %s c %s d %s" % (tmp_path / "elsewhere" / "manifest", root / "x" / "y.toml",
                                         tmp_path / "tools" / "ncs.exe", Path.home() / "secret"))
    assert "<custom data folder>/manifest" in out and "./x" in out
    assert "<ncstool path>" in out and "~/secret" in out
    _no_abs(out)


def test_doctor_and_health_json_have_no_absolute_paths(config):
    forge = Forge.build(config)
    rows = diagnose(forge)
    _no_abs(format_report(rows, verbose=True))
    _no_abs(json.dumps(rows))
    data = next(r for r in rows if r["name"] == "data")
    if config.is_synthetic:
        assert any("data/synthetic (demo set)/manifest" in c["detail"] for c in data["checks"])
