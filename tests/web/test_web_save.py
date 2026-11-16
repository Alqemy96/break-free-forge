"""Web tests for /api/save/*: the real server over HTTP, a throwaway save key, real catalog serials."""
from __future__ import annotations

import base64

import pytest

from tests.save_helpers import STEAM_ID, real_save_yaml, save_forge
from tests.web.test_web import assert_error, running


@pytest.fixture(scope="module")
def sforge(config):
    return save_forge(config)


@pytest.fixture(scope="module")
def web(sforge):
    with running(sforge) as client:
        yield client


@pytest.fixture(scope="module")
def serials(all_serials):
    return all_serials[0], all_serials[2500], all_serials[5000], all_serials[7500]


@pytest.fixture()
def blob(sforge, serials):
    y = real_save_yaml(serials)
    return y, base64.b64encode(sforge.module("save").encrypt_ps5(y)).decode()


def test_open_returns_yaml_summary_and_named_items(web, sforge, blob, serials):
    y, b64 = blob
    r = web.post("/api/save/open", {"data_b64": b64})
    assert r.status == 200, r.text
    d = r.json
    assert d["yaml"] == y and d["summary"]["name"] == "Hunter" and d["summary"]["currencies"]["cash"] == 1000163543
    ops = sforge.module("ops")
    assert [i["serial"] for i in d["items"]] == list(serials)
    assert [i["name"] for i in d["items"]] == [ops.describe(s).display_name for s in serials]
    assert len(d["sha256"]) == 64


def test_items_endpoint_matches_open(web, blob):
    y, b64 = blob
    assert web.post("/api/save/items", {"yaml": y}).json["items"] == web.post("/api/save/open", {"data_b64": b64}).json["items"]


def test_apply_currency_level_and_serial_edits(web, sforge, blob, serials):
    y, _ = blob
    leveled = sforge.module("codec").relevel(serials[1], 31)
    r = web.post("/api/save/apply", {"yaml": y, "edits": [
        {"op": "currency", "name": "eridium", "value": 222},
        {"op": "level", "level": 25},
        {"op": "serial", "ref": "backpack/slot_1", "serial": leveled}]})
    assert r.status == 200, r.text
    d = r.json
    assert [c["line"] for c in d["changed_lines"]] == [6, 15, 23]
    assert d["summary"]["level"] == 25 and d["summary"]["currencies"]["eridium"] == 222
    items = {i.ref: i.serial for i in sforge.module("save").list_items(d["yaml"])}
    assert items["backpack/slot_1"] == leveled and items["backpack/slot_0"] == serials[0]


def test_apply_refusals(web, blob):
    y, _ = blob
    for edits, status, code, needle in (
            ([{"op": "currency", "name": "gold", "value": 1}], 400, "save_error", "no currency"),
            ([{"op": "currency", "name": "cash", "value": -1}], 400, "save_error", "from 0"),
            ([{"op": "serial", "ref": "backpack/slot_0", "serial": "@UgNotASerial"}], 400, "serial_error", None),
            ([{"op": "serial", "ref": "backpack/slot_99", "serial": "@Ugr$WBm/z?c=6VA)YEbK=xgk-+5&!"}], 400, "save_error", "no item"),
            ([{"op": "bogus"}], 400, "bad_request", "unknown op"),
            ([], 400, "bad_request", "edits")):
        assert_error(web.post("/api/save/apply", {"yaml": y, "edits": edits}), status, code, needle)
    assert_error(web.post("/api/save/apply", {"edits": [{"op": "level", "level": 3}]}), 400, "bad_request", "yaml")


def test_write_rewraps_and_verifies(web, sforge, blob):
    y, _ = blob
    r = web.post("/api/save/write", {"yaml": y})
    assert r.status == 200 and r.json["verified"] is True
    raw = base64.b64decode(r.json["data_b64"])
    assert sforge.module("save").decrypt_ps5(raw) == y and r.json["bytes"] == len(raw)
    pc = web.post("/api/save/write", {"yaml": y, "platform": "pc", "steam_id": STEAM_ID}).json
    assert sforge.module("save").decrypt_pc(base64.b64decode(pc["data_b64"]), STEAM_ID) == y
    assert_error(web.post("/api/save/write", {"yaml": y, "platform": "pc"}), 400, "bad_request", "steam_id")
    assert_error(web.post("/api/save/write", {"yaml": y, "platform": "xbox"}), 400, "bad_request", "platform")


def test_open_rejects_bad_input(web, blob):
    assert_error(web.post("/api/save/open", {"data_b64": "!!!"}), 400, "bad_request", "base64")
    assert_error(web.post("/api/save/open", {}), 400, "bad_request", "data_b64")
    other = base64.b64encode(b"\x01" * 32).decode()
    assert_error(web.post("/api/save/open", {"data_b64": other}), 400, "save_error")
    assert_error(web.get("/api/save/open"), 405, "bad_request")


def test_missing_key_is_503_key_missing(config, blob):
    from bl4forge.core.forge import Forge
    with running(Forge.build(config, only=["save", "ops"])) as client:
        err = assert_error(client.post("/api/save/open", {"data_b64": blob[1]}), 503, "key_missing", "ps5_key")
        assert err["message"]
