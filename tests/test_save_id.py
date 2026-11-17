"""Tests for tools/save_id: the file-triage CLI. Synthetic fixtures only (no game data, no game key).

The fixtures are the same ones `--self-test` builds (save_id.make_fixtures). The AES-shaped fixture is made
by the save cell's own container code with a random throwaway key, so it only proves the SHAPE is classified.
"""
from __future__ import annotations

import json
import struct
import zlib

import pytest

from bl4forge.tools import save_id


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    return save_id.make_fixtures(str(tmp_path_factory.mktemp("save_id")))


def test_fixture_set_is_complete(fixtures):
    kinds = {kind for _, kind in fixtures.values()}
    assert kinds <= set(save_id.VERDICT_KINDS)
    for must in ("aes_ecb_candidate", "zlib_trailer_ps5", "plaintext_yaml", "high_entropy_unaligned"):
        assert must in kinds
    assert "aes_shaped_ps5.sav" in fixtures, "the save cell's container should be importable in the repo"


@pytest.mark.parametrize("name", [
    "empty.bin", "random_aligned.sav", "random_unaligned.sav", "plain.yaml", "plain.json", "zlib_only.bin",
    "zlib_ps5_trailer.bin", "zlib_pc_trailer.bin", "header_then_zlib.bin", "gzip.bin", "zstd_magic.bin",
    "pfd.bin", "aes_shaped_ps5.sav",
])
def test_verdict_kind(fixtures, name):
    path, want = fixtures[name]
    assert save_id.identify(path).verdict.kind == want


def test_checks_run_in_order_with_valid_status(fixtures):
    rep = save_id.identify(fixtures["random_aligned.sav"][0])
    assert [c.id for c in rep.checks] == ["size", "entropy", "compression", "console", "strings"]
    assert all(c.status in (save_id.PASS, save_id.FAIL, save_id.INFO) for c in rep.checks)
    assert all(c.detail and "\n" not in c.detail for c in rep.checks)


def test_alignment_check():
    assert save_id.check_size(0).status == save_id.FAIL
    assert save_id.check_size(32).status == save_id.PASS
    assert save_id.check_size(33).status == save_id.INFO
    assert save_id.check_size(33).data["remainder"] == 1


def test_entropy_bounds():
    assert save_id.shannon(b"") == 0.0
    assert save_id.shannon(b"a" * 1000) == 0.0
    assert save_id.shannon(bytes(range(256)) * 4) == pytest.approx(8.0)


def test_encrypted_shape_is_only_consistent_never_confirmed(fixtures):
    v = save_id.identify(fixtures["aes_shaped_ps5.sav"][0]).verdict
    assert v.confidence == "consistent"
    assert "BL4 PS5 shape" in v.stack
    assert any("only a decrypt" in n for n in v.notes)


def test_ps5_trailer_needs_exact_length(tmp_path):
    yaml = save_id.synthetic_yaml(20)
    bad = tmp_path / "bad_trailer.bin"
    bad.write_bytes(zlib.compress(yaml) + struct.pack("<I", len(yaml) + 1))
    assert save_id.identify(str(bad)).verdict.kind == "zlib"


def test_pc_trailer_checks_adler(tmp_path):
    yaml = save_id.synthetic_yaml(20)
    bad = tmp_path / "bad_adler.bin"
    bad.write_bytes(zlib.compress(yaml) + struct.pack("<II", zlib.adler32(yaml) ^ 1, len(yaml)))
    assert save_id.identify(str(bad)).verdict.kind == "zlib"


def test_yaml_flags_from_inflated_payload(fixtures):
    rep = save_id.identify(fixtures["zlib_ps5_trailer.bin"][0])
    strings = {c.id: c for c in rep.checks}["strings"]
    assert strings.data["inner_text"]["yaml"] is True
    assert strings.data["inner_text"]["yaml_state_key"] is True


def test_sibling_hint(tmp_path):
    (tmp_path / "PARAM.SFO").write_bytes(b"\x00PSF" + b"\x00" * 60)
    target = tmp_path / "SAVE.DAT"
    target.write_bytes(bytes(range(256)) * 8)
    console = {c.id: c for c in save_id.identify(str(target)).checks}["console"]
    assert any(s["sibling"] == "PARAM.SFO" for s in console.data["siblings"])


def test_cli_json_is_serialisable(fixtures, capsys):
    assert save_id.main([fixtures["zlib_ps5_trailer.bin"][0], "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"]["kind"] == "zlib_trailer_ps5"
    assert [c["id"] for c in out["checks"]][:2] == ["size", "entropy"]


def test_cli_text_and_missing_file(fixtures, capsys, tmp_path):
    assert save_id.main([fixtures["plain.yaml"][0]]) == 0
    assert "plaintext YAML" in capsys.readouterr().out
    assert save_id.main([str(tmp_path / "nope.bin")]) == 2


def test_self_test_passes():
    assert save_id.self_test(verbose=False) == 0


def test_report_never_carries_raw_bytes(fixtures):
    for path, _ in fixtures.values():
        json.dumps(save_id.identify(path).to_dict())     # raises TypeError on bytes
