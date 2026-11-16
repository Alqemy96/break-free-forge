"""CLI tests for the save commands. A throwaway key and a small save built around real catalog serials;
the real forge modules (save, ops and their neighbours) do the work."""
from __future__ import annotations

import json

import pytest

from bl4forge.cli import main
from tests.save_helpers import STEAM_ID, real_save_yaml, save_forge


@pytest.fixture(scope="module")
def sforge(config):
    return save_forge(config)


@pytest.fixture(scope="module")
def serials(all_serials):
    return all_serials[0], all_serials[2500], all_serials[5000], all_serials[7500]


@pytest.fixture()
def sav(tmp_path, sforge, serials):
    """A PS5 save file on disk (and its bytes), encrypted with the throwaway key."""
    yaml_text = real_save_yaml(serials)
    p = tmp_path / "gbxsavegame.sav"
    p.write_bytes(sforge.module("save").encrypt_ps5(yaml_text))
    return p, yaml_text


def run(capsys, argv, forge):
    capsys.readouterr()
    code = main(list(argv), forge=forge)
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def test_open_shows_decoded_gear_with_names(capsys, sforge, sav, serials):
    p, _ = sav
    code, out, err = run(capsys, ["save-open", "--file", str(p), "--json"], sforge)
    assert code == 0, err
    data = json.loads(out)
    assert data["summary"]["name"] == "Hunter" and data["summary"]["level"] == 22
    assert [i["ref"] for i in data["items"]] == ["backpack/slot_0", "backpack/slot_1", "equipped/slot_3", "lostloot/0"]
    ops = sforge.module("ops")
    for item, serial in zip(data["items"], serials):
        info = ops.describe(serial)
        assert item["serial"] == serial and item["name"] == info.display_name and item["level"] == info.level
        assert item["name"] and item["error"] is None
    code, text, _ = run(capsys, ["save-open", "--file", str(p)], sforge)
    assert code == 0 and "Character:  Hunter" in text and data["items"][0]["name"] in text


def test_open_reports_an_undecodable_serial_instead_of_dropping_it(capsys, sforge, tmp_path, serials):
    y = real_save_yaml(serials).replace(serials[1], "@UgNotASerial")
    p = tmp_path / "x.sav"
    p.write_bytes(sforge.module("save").encrypt_ps5(y))
    code, out, _ = run(capsys, ["save-items", "--file", str(p), "--json"], sforge)
    rows = json.loads(out)
    assert code == 0 and len(rows) == 4 and rows[1]["error"] and rows[1]["name"] is None


def test_items_filters(capsys, sforge, sav, serials):
    p, _ = sav
    code, out, _ = run(capsys, ["save-items", "--file", str(p), "--area", "backpack", "--serials"], sforge)
    assert code == 0 and out.split() == [serials[0], serials[1]]


def test_set_currency_writes_a_copy_with_one_changed_line(capsys, sforge, sav, tmp_path):
    p, y = sav
    before = p.read_bytes()
    dst = tmp_path / "edited.sav"
    code, out, err = run(capsys, ["save-set-currency", "--file", str(p), "--name", "eridium", "--value", "222",
                                  "--out", str(dst)], sforge)
    assert code == 0, err
    assert "1 line(s) changed" in out and "+ eridium: 222" in out and "unchanged" in out
    assert p.read_bytes() == before                                    # the source is untouched
    save = sforge.module("save")
    new = save.decrypt_ps5(dst.read_bytes())
    assert [(n, b.strip(), a.strip()) for n, b, a in save.changed_lines(y, new)] == [
        (23, "eridium: 1000001124", "eridium: 222")]
    assert (tmp_path / "edited.sav.bl4forge.json").is_file()


def test_set_currency_refusals(capsys, sforge, sav, tmp_path):
    p, _ = sav
    dst = tmp_path / "e.sav"
    taken = tmp_path / "taken.sav"
    taken.write_bytes(b"keep me")
    for argv, needle in (
            (["--name", "gold", "--value", "1", "--out", str(dst)], "no currency"),
            (["--name", "cash", "--value", "-4", "--out", str(dst)], "from 0"),
            (["--name", "cash", "--value", "4", "--out", str(p)], "refusing to write over the source"),
            (["--name", "cash", "--value", "4", "--out", str(taken)], "already exists"),
            (["--name", "cash", "--value", "4"], "--out is required")):
        code, out, err = run(capsys, ["save-set-currency", "--file", str(p)] + argv, sforge)
        assert code == 2 and err.startswith("error: ") and needle in err, (argv, err)
    code, _, err = run(capsys, ["save-set-currency", "--file", str(p), "--name", "cash", "--value", "4",
                                "--out", str(p), "--overwrite"], sforge)
    assert code == 2 and "refusing to write over the source" in err
    assert not dst.exists() and taken.read_bytes() == b"keep me"


def test_dry_run_writes_nothing(capsys, sforge, sav, tmp_path):
    p, _ = sav
    code, out, _ = run(capsys, ["save-set-currency", "--file", str(p), "--name", "cash", "--value", "1",
                                "--dry-run"], sforge)
    assert code == 0 and "dry run" in out and list(tmp_path.iterdir()) == [p]


def test_set_serial_round_trips_through_the_codec(capsys, sforge, sav, tmp_path, serials):
    p, _ = sav
    codec = sforge.module("codec")
    leveled = codec.relevel(serials[0], 30)
    assert leveled != serials[0]
    dst = tmp_path / "edited.sav"
    code, out, err = run(capsys, ["save-set-serial", "--file", str(p), "--ref", "backpack/slot_0",
                                  "--serial", leveled, "--out", str(dst)], sforge)
    assert code == 0, err
    assert "1 line(s) changed" in out and "level 30" in out
    save = sforge.module("save")
    items = {i.ref: i.serial for i in save.list_items(save.decrypt_ps5(dst.read_bytes()))}
    assert items["backpack/slot_0"] == leveled
    assert codec.get_level(codec.decode(items["backpack/slot_0"])) == 30
    assert codec.encode(codec.decode(items["backpack/slot_0"])) == leveled
    assert items["backpack/slot_1"] == serials[1]                      # everything else unchanged


def test_set_serial_refuses_junk(capsys, sforge, sav, tmp_path):
    p, _ = sav
    code, _, err = run(capsys, ["save-set-serial", "--file", str(p), "--ref", "backpack/slot_0",
                                "--serial", "@UgNotASerial", "--out", str(tmp_path / "e.sav")], sforge)
    assert code == 2 and err.startswith("error: ") and not (tmp_path / "e.sav").exists()
    code, _, err = run(capsys, ["save-set-serial", "--file", str(p), "--ref", "backpack/slot_9",
                                "--serial", "@UgNotASerial", "--out", str(tmp_path / "e.sav")], sforge)
    assert code == 2 and not (tmp_path / "e.sav").exists()


def test_set_level(capsys, sforge, sav, tmp_path):
    p, y = sav
    dst = tmp_path / "e.sav"
    code, out, err = run(capsys, ["save-set-level", "--file", str(p), "--level", "30", "--xp", "999",
                                  "--out", str(dst)], sforge)
    assert code == 0 and "2 line(s) changed" in out, err
    s = sforge.module("save").summary(sforge.module("save").decrypt_ps5(dst.read_bytes()))
    assert (s["level"], s["points"]) == (30, 999)
    code, _, err = run(capsys, ["save-set-level", "--file", str(p), "--out", str(dst)], sforge)
    assert code == 2 and "--level and/or --xp" in err


def test_decrypt_to_yaml(capsys, sforge, sav, tmp_path):
    p, y = sav
    dst = tmp_path / "save.yaml"
    code, out, _ = run(capsys, ["save-decrypt", "--file", str(p), "--out", str(dst)], sforge)
    assert code == 0 and dst.read_text(encoding="utf-8") == y


def test_pc_platform_needs_an_id_and_round_trips(capsys, sforge, tmp_path, serials):
    y = real_save_yaml(serials)
    p = tmp_path / "pc.sav"
    p.write_bytes(sforge.module("save").encrypt_pc(y, STEAM_ID))
    code, _, err = run(capsys, ["save-open", "--file", str(p), "--platform", "pc"], sforge)
    assert code == 2 and "--steam-id" in err
    code, out, err = run(capsys, ["save-set-currency", "--file", str(p), "--platform", "pc", "--steam-id", STEAM_ID,
                                  "--name", "cash", "--value", "5", "--out", str(tmp_path / "pc2.sav")], sforge)
    assert code == 0, err
    assert sforge.module("save").summary(
        sforge.module("save").decrypt_pc((tmp_path / "pc2.sav").read_bytes(), STEAM_ID))["currencies"]["cash"] == 5


def test_missing_key_is_a_clear_error(capsys, config, tmp_path):
    from bl4forge.core.forge import Forge
    p = tmp_path / "a.sav"
    p.write_bytes(b"\x00" * 32)
    code, out, err = run(capsys, ["save-open", "--file", str(p)], Forge.build(config, only=["save", "ops"]))
    assert code == 2 and "ps5_key" in err and "Traceback" not in err


def test_missing_file(capsys, sforge, tmp_path):
    code, _, err = run(capsys, ["save-open", "--file", str(tmp_path / "nope.sav")], sforge)
    assert code == 2 and "no such save file" in err


_PROFILE = (
    "domains: \n  local: \n    progression_shared: \n      graphs: \n      - name: sdu_upgrades\n"
    "        nodes: \n        - name: A\n          points_spent: 5\n        - name: B\n          points_spent: 10\n"
    "      point_pools: \n        echotokenprogresspoints: 140\n"
)


def test_set_point_pool_round_trip_and_open(capsys, sforge, tmp_path):
    save = sforge.module("save")
    p = tmp_path / "profile.sav"
    p.write_bytes(save.encrypt_ps5(_PROFILE))
    before = p.read_bytes()
    code, out, _ = run(capsys, ["save-open", "--file", str(p)], sforge)
    assert code == 0 and "Echo tokens: 140 earned, 15 spent (sdu_upgrades), 125 available" in out
    dst = tmp_path / "edited.sav"
    code, out, err = run(capsys, ["save-set-point-pool", "--file", str(p), "--name", "echotokenprogresspoints",
                                  "--value", "1000", "--out", str(dst)], sforge)
    assert code == 0, err
    assert "1 line(s) changed" in out and "+ echotokenprogresspoints: 1000" in out and "985 available" in out
    assert p.read_bytes() == before
    new = save.decrypt_ps5(dst.read_bytes())
    assert new == _PROFILE.replace("140", "1000")
    assert (tmp_path / "edited.sav.bl4forge.json").is_file()
    code, out, _ = run(capsys, ["save-open", "--file", str(dst), "--json"], sforge)
    assert json.loads(out)["echo_tokens"]["value"] == 1000


def test_set_point_pool_refusals(capsys, sforge, tmp_path):
    p = tmp_path / "profile.sav"
    p.write_bytes(sforge.module("save").encrypt_ps5(_PROFILE))
    for argv, needle in ((["--name", "gold", "--value", "1", "--out", str(tmp_path / "e.sav")], "no shared point pool"),
                         (["--name", "echotokenprogresspoints", "--value", "-1", "--out", str(tmp_path / "e.sav")], "from 0"),
                         (["--name", "echotokenprogresspoints", "--value", "1", "--out", str(p)], "refusing to write over")):
        code, _, err = run(capsys, ["save-set-point-pool", "--file", str(p)] + argv, sforge)
        assert code == 2 and needle in err, (argv, err)
    assert not (tmp_path / "e.sav").exists()
