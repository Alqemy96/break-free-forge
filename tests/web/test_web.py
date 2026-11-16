"""Tests for the web layer (outer layer). The REAL server runs on an ephemeral port against a REAL
Forge and is exercised over HTTP with http.client; expectations are computed by calling the modules
directly, so the server is checked against the ports, not against itself."""
from __future__ import annotations

import contextlib
import dataclasses
import html as htmllib
import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from bl4forge.core import vocab
from bl4forge.core.config import Config
from bl4forge.core.doctor import diagnose
from bl4forge.core.forge import Forge
from bl4forge.core.module import Module
from bl4forge.core.ports import RenderPort, OpsPort
from bl4forge.core.types import HealthReport, LoadoutItem, LoadoutRequest, SearchQuery
from bl4forge.web import MAX_BODY, PortInUse, create_server, host_allowed
from tests.dataset import D

ROOT = Path(__file__).resolve().parents[2]
JSON_CT = {"Content-Type": "application/json"}
STRUCTURAL = "passed structural checks only; in-game validity is not guaranteed"

README_EXAMPLES = {
    "cryo loadout": [
        {"group": "Weapons", "type": "shotgun", "element": "cryo", "query": D.SHOTGUN_Q},
        {"group": "Weapons", "type": "sniper", "element": "cryo"},
        {"group": "Gear", "query": D.GEAR_Q, "element": "cryo"},
        {"group": "Gear", "type": "classmod"},
        {"group": "Gear", "type": "repkit"},
        {"group": "Gear", "type": "grenade"},
    ],
    "wombo combo + plasma coil + cryo super soldier": [
        {"group": "Weapons", "query": D.WOMBO_Q, "element": "cryo"},
        {"group": "Weapons", "query": D.PLASMA_Q},
        {"group": "Gear", "query": D.GEAR_Q, "element": "cryo"},
    ],
    "level 60 radiation shotgun": [
        {"type": "shotgun", "element": "radiation"},
    ],
}


# ---- a tiny HTTP client ------------------------------------------------------------------------------

class Resp:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body

    def header(self, name, default=None):
        return self.headers.get(name.lower(), default)

    @property
    def json(self):
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self):
        return self.body.decode("utf-8")


class Client:
    def __init__(self, server):
        self.port = server.server_address[1]

    def request(self, method, path, body=None, raw=None, headers=None):
        """`body` is JSON-encoded (with the JSON content type); `raw` is sent as is."""
        hdrs = dict(headers or {})
        data = raw
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            conn.request(method, path, body=data, headers=hdrs)
            r = conn.getresponse()
            payload = r.read()
            return Resp(r.status, {k.lower(): v for k, v in r.getheaders()}, payload)
        finally:
            conn.close()

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body=body, **kw)

    def raw_socket(self, data: bytes) -> Resp:
        """Send hand-made bytes (malformed or unusual requests) and parse the answer."""
        with socket.create_connection(("127.0.0.1", self.port), timeout=20) as s:
            s.sendall(data)
            chunks = []
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        blob = b"".join(chunks)
        head, _, payload = blob.partition(b"\r\n\r\n")
        lines = head.decode("iso-8859-1").split("\r\n")
        status = int(lines[0].split()[1])
        headers = {}
        for line in lines[1:]:
            k, _, v = line.partition(":")
            headers[k.strip().lower()] = v.strip()
        return Resp(status, headers, payload)


def assert_error(resp: Resp, status: int, code: str, needle: str = None):
    assert resp.status == status, (resp.status, resp.body[:300])
    assert resp.header("content-type", "").startswith("application/json")
    body = resp.json
    assert set(body) == {"error"} and {"code", "message"} <= set(body["error"]), body
    assert body["error"]["code"] == code, body
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert "Traceback" not in resp.text and "File \"" not in resp.text
    if needle:
        assert needle.lower() in body["error"]["message"].lower(), body
    return body["error"]


@contextlib.contextmanager
def running(forge, **kw):
    server = create_server(forge, host="127.0.0.1", port=0, quiet=True, **kw)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield Client(server)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


# ---- fixtures ----------------------------------------------------------------------------------------

@pytest.fixture(scope="session")
def web(forge):
    with running(forge) as client:
        yield client


@pytest.fixture(scope="session")
def serials(forge):
    """Real serials at their stored level 50, plus a same-category pair for swaps."""
    cat, codec = forge.catalog, forge.codec
    shotgun = cat.search(SearchQuery(query=D.SHOTGUN_Q, element="cryo", type="shotgun", limit=1)).entries[0].serial
    shield = cat.search(SearchQuery(type="shield", limit=1)).entries[0].serial
    classmod = cat.search(SearchQuery(type="classmod", character="gravitar", limit=1)).entries[0].serial
    repkit = cat.search(SearchQuery(type="repkit", limit=1)).entries[0].serial
    by_cat = {}
    for e in cat.search(SearchQuery(type="shotgun", limit=400)).entries:
        by_cat.setdefault(codec.get_category_id(codec.decode(e.serial)), []).append(e.serial)
    a, b = next(v[:2] for v in by_cat.values() if len(v) >= 2)
    return {"shotgun": shotgun, "shield": shield, "classmod": classmod, "repkit": repkit, "pair": (a, b)}


def rt(obj):
    """What a value looks like after a JSON round trip (tuples become lists)."""
    return json.loads(json.dumps(obj))


# ---- meta / health / stats -----------------------------------------------------------------------------

def test_meta(web, forge):
    r = web.get("/api/meta")
    assert r.status == 200 and r.header("content-type") == "application/json; charset=utf-8"
    m = r.json
    assert set(m) == {"version", "level", "character", "owned_packs", "catalog_count", "manifest_version",
                      "elements", "rarities", "characters", "types"}
    assert m["level"] == forge.config.level and m["character"] == forge.config.character
    assert m["owned_packs"] == list(forge.config.owned_packs)
    assert m["catalog_count"] == forge.catalog.count() == D.CATALOG_ROWS
    assert m["manifest_version"] == forge.data.manifest_version()
    assert m["elements"] == [{"id": e, "label": vocab.ELEMENT_LABELS[e]} for e in vocab.ELEMENTS]
    assert m["rarities"] == list(vocab.RARITIES) and m["characters"] == list(vocab.CHARACTERS)
    ids = [t["id"] for t in m["types"]]
    assert ids[:2] == ["pistol", "shotgun"] and ids[-5:] == ["shield", "classmod", "repkit", "grenade", "enhancement"]
    assert all(set(t) == {"id", "label", "group"} for t in m["types"])
    assert {t["group"] for t in m["types"] if t["id"] in ("pistol", "sniper", "heavy")} == {"weapon"}


def test_every_advertised_type_finds_items(web, forge):
    for t in web.get("/api/meta").json["types"]:
        res = forge.catalog.search(SearchQuery(type=t["id"], limit=1, include_unowned=True))
        assert res.entries, "type %r from /api/meta matches nothing in the catalog" % t["id"]


def test_health_is_the_doctor(web, forge):
    r = web.get("/api/health")
    assert r.status == 200
    body = r.json
    assert body["ok"] is True and body["modules"] == rt(diagnose(forge))
    assert {m["name"] for m in body["modules"]} == set(forge.states)


def test_stats_verbatim(web, forge):
    r = web.get("/api/stats")
    assert r.status == 200 and r.json == rt(forge.catalog.stats())
    assert r.json["by_type"]["weapon"] > 0


# ---- search ---------------------------------------------------------------------------------------------

SEARCHES = [
    {"query": D.SHOTGUN_Q, "type": "shotgun", "element": "cryo", "limit": 5},
    {"type": "sniper", "element": "electric", "limit": 10},                  # alias -> shock
    {"query": D.GEAR_Q, "rarity": "legendary", "limit": 3},
    {"type": "ar", "manufacturer": D.AR_MFR, "limit": 7},
    {"type": "shield", "limit": 25},
    {"type": "classmod", "character": "paladin", "limit": 4},
    {"type": "repkit", "limit": 2},
    {"type": "grenade", "limit": 2},
    {"element": "corrosive", "type": "pistol", "limit": 200},
    {"query": "zzzz-nothing-matches-this"},
]


def _qs(params):
    from urllib.parse import urlencode
    return urlencode({k: v for k, v in params.items()})


@pytest.mark.parametrize("params", SEARCHES, ids=[_qs(p)[:50] for p in SEARCHES])
def test_search_equals_catalog_search(web, forge, params):
    expected = forge.catalog.search(SearchQuery(**params))
    r = web.get("/api/search?" + _qs(params))
    assert r.status == 200
    body = r.json
    assert set(body) == {"count", "level", "results", "hidden", "dropped_element_mismatch", "notes"}
    assert body["level"] is None and body["count"] == len(expected.entries) == len(body["results"])
    assert [x["serial"] for x in body["results"]] == [e.serial for e in expected.entries]
    assert body["dropped_element_mismatch"] == expected.dropped_element_mismatch
    assert body["hidden"] == []
    for row, entry in zip(body["results"], expected.entries):
        assert set(row) == {"serial", "name", "type", "weapon_type", "manufacturer", "label", "rarity",
                            "element", "source", "level", "decoded"}
        for key in ("name", "type", "weapon_type", "manufacturer", "label", "rarity", "element", "source"):
            assert row[key] == getattr(entry, key)            # catalog hints, verbatim
        info = forge.ops.describe(entry.serial)
        assert row["level"] == info.level == 50               # not re-leveled without `level`
        assert row["decoded"] == {"display_name": info.display_name, "category": info.category,
                                  "rarity": info.rarity, "element": info.element, "owned": info.owned,
                                  "warnings": list(info.warnings)}


def test_search_relevels_with_ops(web, forge):
    r = web.get("/api/search?type=shotgun&element=cryo&limit=6&level=60")
    body = r.json
    assert r.status == 200 and body["level"] == 60 and body["count"] > 0
    expected = forge.catalog.search(SearchQuery(type="shotgun", element="cryo", limit=6))
    for row, entry in zip(body["results"], expected.entries):
        assert row["serial"] == forge.ops.relevel(entry.serial, 60) != entry.serial
        assert row["level"] == 60 and forge.codec.get_level(forge.codec.decode(row["serial"])) == 60
        assert row["decoded"]["display_name"] == forge.ops.describe(row["serial"]).display_name
    low = web.get("/api/search?type=shotgun&limit=1&level=1").json
    assert low["results"][0]["level"] == 1


def test_search_defaults_to_25_and_caps_at_200(web):
    assert web.get("/api/search?type=shield").json["count"] == 25
    assert web.get("/api/search?type=shield&limit=200").json["count"] == 200
    assert web.get("/api/search?type=shield&limit=1").json["count"] == 1


@pytest.mark.parametrize("query", [
    "limit=0", "limit=201", "limit=-3", "limit=abc", "limit=1.5", "level=0", "level=101", "level=sixty",
    "include_unowned=maybe", "verify_element=2", "element=plasma",
])
def test_search_bad_parameters(web, query):
    assert_error(web.get("/api/search?" + query), 400, "bad_request")


def test_search_blank_parameters_are_absent(web, forge):
    r = web.get("/api/search?query=&type=shield&element=&manufacturer=&rarity=&character=&limit=3&level=&include_unowned=")
    assert r.status == 200 and r.json["count"] == 3
    assert [x["serial"] for x in r.json["results"]] == [
        e.serial for e in forge.catalog.search(SearchQuery(type="shield", limit=3)).entries]


def test_search_classmod_defaults_to_configured_character(web, forge):
    r = web.get("/api/search?type=classmod&limit=5").json
    expected = forge.catalog.search(SearchQuery(type="classmod", character=forge.config.character, limit=5))
    assert [x["serial"] for x in r["results"]] == [e.serial for e in expected.entries]
    assert len(r["notes"]) == 1 and forge.config.character in r["notes"][0]
    explicit = web.get("/api/search?type=class_mod&character=paladin&limit=5").json
    assert explicit["notes"] == []
    assert [x["serial"] for x in explicit["results"]] == [
        e.serial for e in forge.catalog.search(SearchQuery(type="classmod", character="paladin", limit=5)).entries]
    assert web.get("/api/search?type=shield&limit=1").json["notes"] == []


def test_search_verify_element_flag(web, forge):
    q = dict(type="pistol", element="fire", limit=200)
    on = web.get("/api/search?" + _qs(q)).json
    off = web.get("/api/search?" + _qs(dict(q, verify_element="0"))).json
    exp_on = forge.catalog.search(SearchQuery(**q))
    exp_off = forge.catalog.search(SearchQuery(**q, verify_element=False))
    assert [x["serial"] for x in on["results"]] == [e.serial for e in exp_on.entries]
    assert [x["serial"] for x in off["results"]] == [e.serial for e in exp_off.entries]
    assert off["dropped_element_mismatch"] == 0 and on["dropped_element_mismatch"] == exp_on.dropped_element_mismatch


def test_search_reports_hidden_packs_and_labels(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[ownership]\npacks = ["coregame","bounty_pack_1","bounty_pack_2","bounty_pack_4","bounty_pack_5"]\n',
                   encoding="utf-8")
    forge = Forge.build(Config.load(path=cfg))
    with running(forge) as web:
        label = forge.rules.pack_label("bounty_pack_3")
        r = web.get("/api/search?query=frangible&limit=100").json
        assert r["hidden"] == [{"pack": "bounty_pack_3", "label": label, "count": 26}]
        assert all(x["decoded"]["owned"] for x in r["results"])
        shown = web.get("/api/search?query=frangible&limit=100&include_unowned=1").json
        assert shown["hidden"] == [] and shown["count"] == r["count"] + 26
        assert sum(1 for x in shown["results"] if not x["decoded"]["owned"]) == 26
        meta = web.get("/api/meta").json
        assert "bounty_pack_3" not in meta["owned_packs"]


def test_search_relevel_failure_is_a_warning(web, forge, monkeypatch):
    from bl4forge.core.errors import SerialError

    def refuse(serial, level):
        raise SerialError("nope")
    monkeypatch.setattr(forge.ops, "relevel", refuse)
    r = web.get("/api/search?type=shield&limit=2&level=60").json
    expected = forge.catalog.search(SearchQuery(type="shield", limit=2)).entries
    assert [x["serial"] for x in r["results"]] == [e.serial for e in expected]     # stored code, not pretended
    assert all(any("re-level to 60 failed" in w for w in x["decoded"]["warnings"]) for x in r["results"])
    assert all(x["level"] == 50 for x in r["results"])


# ---- identify -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["shotgun", "shield", "classmod", "repkit"])
def test_identify_equals_ops(web, forge, serials, kind):
    serial = serials[kind]
    r = web.post("/api/identify", {"serial": serial})
    assert r.status == 200
    body = r.json
    assert set(body) == {"serial", "info", "odds", "parts", "problems", "is_weapon", "can_set_element"}
    info = forge.ops.describe(serial)
    assert body["serial"] == serial and body["info"] == rt(info.to_dict())
    assert body["odds"] == forge.ops.format_odds(forge.ops.rarity_estimate(info))
    assert body["problems"] == forge.rules.validate(serial)
    parts = forge.ops.part_list(serial)
    assert body["parts"] == [{"position": i, "token_index": p.token_index, "label": p.label(),
                              "category_id": p.category_id, "index": p.index, "raw": p.raw,
                              "category_link": p.category_link} for i, p in enumerate(parts)]
    assert [p["position"] for p in body["parts"]] == list(range(len(parts)))
    is_weapon = kind == "shotgun"
    assert body["is_weapon"] is is_weapon and body["can_set_element"] is is_weapon
    assert body["is_weapon"] == forge.data.is_weapon_category(info.category_id)


def test_identify_with_level_releveles_first(web, forge, serials):
    r = web.post("/api/identify", {"serial": serials["shotgun"], "level": 60})
    assert r.status == 200
    assert r.json["serial"] == forge.ops.relevel(serials["shotgun"], 60)
    assert r.json["info"]["level"] == 60 and r.json["info"]["serial"] == r.json["serial"]


def test_identify_tolerates_surrounding_whitespace(web, serials):
    r = web.post("/api/identify", {"serial": "  %s\n" % serials["shield"]})
    assert r.status == 200 and r.json["serial"] == serials["shield"]


@pytest.mark.parametrize("body, status, code", [
    ({}, 400, "bad_request"),
    ({"serial": ""}, 400, "bad_request"),
    ({"serial": "   "}, 400, "bad_request"),
    ({"serial": 12345}, 400, "bad_request"),
    ({"serial": ["@U"]}, 400, "bad_request"),
    ({"serial": "garbage"}, 400, "serial_error"),
    ({"serial": "@U"}, 400, "serial_error"),
    ({"serial": "@Ugxx"}, 400, "serial_error"),
])
def test_identify_errors(web, body, status, code):
    assert_error(web.post("/api/identify", body), status, code)


@pytest.mark.parametrize("level", [0, 101, -1, "60", 60.5, True, [60], {"a": 1}])
def test_identify_bad_level(web, serials, level):
    assert_error(web.post("/api/identify", {"serial": serials["shield"], "level": level}), 400, "bad_request")


# ---- transform ------------------------------------------------------------------------------------------

def check_transform_payload(body, forge, new_serial, previous):
    assert set(body) >= {"serial", "info", "odds", "parts", "problems", "is_weapon", "can_set_element",
                         "previous", "note"}
    assert body["serial"] == new_serial and body["previous"] == previous
    assert body["info"] == rt(forge.ops.describe(new_serial).to_dict())
    assert isinstance(body["note"], str)


def test_transform_relevel(web, forge, serials):
    for kind in ("shotgun", "shield", "classmod"):
        r = web.post("/api/transform", {"serial": serials[kind], "op": "relevel", "level": 60})
        assert r.status == 200
        expected = forge.ops.relevel(serials[kind], 60)
        check_transform_payload(r.json, forge, expected, serials[kind])
        assert r.json["info"]["level"] == 60


@pytest.mark.parametrize("element", ["fire", "cryo", "radiation", "shock", "corrosive", "impact", "Electric", "ICE"])
def test_transform_set_element_equals_ops(web, forge, serials, element):
    serial = serials["shotgun"]
    r = web.post("/api/transform", {"serial": serial, "op": "set_element", "element": element})
    assert r.status == 200
    canonical = vocab.normalize_element(element)
    expected = forge.ops.set_element(serial, canonical)
    check_transform_payload(r.json, forge, expected, serial)
    assert r.json["info"]["element"] == canonical
    assert r.json["can_set_element"] is True
    if expected == serial:
        assert "unchanged" in r.json["note"]


def test_transform_set_element_round_trips(web, forge, serials):
    serial = serials["shotgun"]                                   # a cryo shotgun
    fire = web.post("/api/transform", {"serial": serial, "op": "set_element", "element": "fire"}).json
    assert fire["info"]["element"] == "fire" and fire["serial"] != serial
    back = web.post("/api/transform", {"serial": fire["serial"], "op": "set_element", "element": "cryo"}).json
    assert back["serial"] == serial                               # replacing an element is byte-exact
    impact = web.post("/api/transform", {"serial": serial, "op": "set_element", "element": "impact"}).json
    assert impact["info"]["element"] == "impact" and impact["serial"] != serial


@pytest.mark.parametrize("kind", ["shield", "classmod", "repkit"])
def test_transform_set_element_refused_for_gear(web, serials, kind):
    err = assert_error(web.post("/api/transform", {"serial": serials[kind], "op": "set_element", "element": "fire"}),
                       400, "bad_request", "weapon")
    assert "gear" in err["message"]


def test_transform_set_element_bad_element(web, serials):
    assert_error(web.post("/api/transform", {"serial": serials["shotgun"], "op": "set_element", "element": "plasma"}),
                 400, "bad_request", "unknown element")
    assert_error(web.post("/api/transform", {"serial": serials["shotgun"], "op": "set_element"}), 400, "bad_request")


def test_transform_reseed_with_seed(web, forge, serials):
    serial = serials["shotgun"]
    r = web.post("/api/transform", {"serial": serial, "op": "reseed", "seed": 123})
    assert r.status == 200
    expected = forge.ops.set_seed(serial, 123)
    check_transform_payload(r.json, forge, expected, serial)
    assert r.json["seed"] == 123 and forge.ops.get_seed(r.json["serial"]) == 123
    assert "seed 123" in r.json["note"]
    for edge in (0, 2 ** 31 - 1):
        e = web.post("/api/transform", {"serial": serial, "op": "reseed", "seed": edge})
        assert e.status == 200 and forge.ops.get_seed(e.json["serial"]) == edge


def test_transform_reseed_without_seed_is_random(web, forge, serials):
    serial = serials["shield"]
    seeds = set()
    for _ in range(3):
        r = web.post("/api/transform", {"serial": serial, "op": "reseed"})
        assert r.status == 200
        seed = r.json["seed"]
        assert isinstance(seed, int) and 0 <= seed <= 2 ** 31 - 1
        assert forge.ops.get_seed(r.json["serial"]) == seed
        assert r.json["serial"] == forge.ops.set_seed(serial, seed)
        seeds.add(seed)
    assert len(seeds) == 3                                         # SystemRandom: collisions are ~2**-30


@pytest.mark.parametrize("seed", [-1, 2 ** 31, "5", 1.5, True, [1]])
def test_transform_reseed_bad_seed(web, serials, seed):
    assert_error(web.post("/api/transform", {"serial": serials["shotgun"], "op": "reseed", "seed": seed}),
                 400, "bad_request")


def test_transform_swap_equals_ops_and_notes_structural_checks(web, forge, serials):
    a, b = serials["pair"]
    r = web.post("/api/transform", {"serial": a, "op": "swap", "source": b, "positions": [3, 4]})
    assert r.status == 200
    expected = forge.ops.swap_parts(a, b, [3, 4])
    check_transform_payload(r.json, forge, expected, a)
    assert r.json["problems"] == [] and STRUCTURAL in r.json["note"]


def test_transform_swap_that_breaks_structure_says_so(web, forge, serials):
    a, b = serials["pair"]
    r = web.post("/api/transform", {"serial": a, "op": "swap", "source": b, "positions": [3]})
    assert r.status == 200
    check_transform_payload(r.json, forge, forge.ops.swap_parts(a, b, [3]), a)
    assert r.json["problems"], "swapping part 3 of this pair is known to give two element parts"
    assert r.json["problems"][0] in r.json["note"]
    assert "not pass structural checks" in r.json["note"] and STRUCTURAL not in r.json["note"]
    assert "not guaranteed" in r.json["note"]


def test_transform_swap_cross_category(web, forge, serials):
    a, shield = serials["shotgun"], serials["shield"]
    refused = web.post("/api/transform", {"serial": a, "op": "swap", "source": shield, "positions": [1]})
    assert_error(refused, 400, "serial_error", "categories")
    for flag in (False, None):
        body = {"serial": a, "op": "swap", "source": shield, "positions": [1], "allow_cross": flag}
        assert_error(web.post("/api/transform", body), 400, "serial_error")
    ok = web.post("/api/transform", {"serial": a, "op": "swap", "source": shield, "positions": [1],
                                     "allow_cross": True})
    assert ok.status == 200
    assert ok.json["serial"] == forge.ops.swap_parts(a, shield, [1], allow_cross=True)


@pytest.mark.parametrize("extra", [
    {"positions": []}, {"positions": "3"}, {"positions": [True]}, {"positions": ["1"]}, {"positions": [-1]},
    {"positions": [1.5]}, {}, {"positions": [1], "source": ""}, {"positions": [1], "allow_cross": "perhaps"},
])
def test_transform_swap_bad_arguments(web, serials, extra):
    a, b = serials["pair"]
    body = dict({"serial": a, "op": "swap", "source": b}, **extra)
    if extra.get("source") == "":
        body["source"] = ""
    assert_error(web.post("/api/transform", body), 400, "bad_request")


def test_transform_swap_position_out_of_range_and_bad_source(web, serials):
    a, b = serials["pair"]
    assert_error(web.post("/api/transform", {"serial": a, "op": "swap", "source": b, "positions": [999]}),
                 400, "serial_error")
    assert_error(web.post("/api/transform", {"serial": a, "op": "swap", "source": "garbage", "positions": [1]}),
                 400, "serial_error")


@pytest.mark.parametrize("body", [
    {"op": "relevel", "level": 60},
    {"serial": "SERIAL"},
    {"serial": "SERIAL", "op": ""},
    {"serial": "SERIAL", "op": "explode"},
    {"serial": "SERIAL", "op": "RELEVEL", "level": 60},
    {"serial": "SERIAL", "op": 7},
    {"serial": "SERIAL", "op": "relevel"},
    {"serial": "SERIAL", "op": "relevel", "level": 0},
    {"serial": "SERIAL", "op": "relevel", "level": 101},
])
def test_transform_bad_requests(web, serials, body):
    body = {k: (serials["shield"] if v == "SERIAL" else v) for k, v in body.items()}
    assert_error(web.post("/api/transform", body), 400, "bad_request")


@pytest.mark.parametrize("op, extra", [("relevel", {"level": 60}), ("set_element", {"element": "fire"}),
                                       ("reseed", {"seed": 1}), ("swap", {"source": "x", "positions": [1]})])
def test_transform_garbage_serial_is_serial_error(web, op, extra):
    assert_error(web.post("/api/transform", dict({"serial": "garbage", "op": op}, **extra)), 400, "serial_error")


# ---- diff -----------------------------------------------------------------------------------------------

def test_diff_equals_ops(web, forge, serials):
    a, b = serials["pair"]
    r = web.post("/api/diff", {"a": a, "b": b})
    assert r.status == 200 and set(r.json) == {"rows"}
    assert r.json["rows"] == rt(forge.ops.diff(a, b)) and r.json["rows"]
    assert all(set(row) == {"field", "a", "b"} for row in r.json["rows"])
    same = web.post("/api/diff", {"a": a, "b": a})
    assert same.status == 200 and same.json == {"rows": []}
    fire = forge.ops.set_element(serials["shotgun"], "fire")
    el = web.post("/api/diff", {"a": serials["shotgun"], "b": fire}).json["rows"]
    assert {"field": "element", "a": "cryo", "b": "fire"} in el


@pytest.mark.parametrize("body, code", [({}, "bad_request"), ({"a": "x"}, "bad_request"), ({"b": "x"}, "bad_request"),
                                        ({"a": 1, "b": 2}, "bad_request"), ({"a": "garbage", "b": "garbage"}, "serial_error")])
def test_diff_errors(web, body, code):
    assert_error(web.post("/api/diff", body), 400, code)


# ---- build ----------------------------------------------------------------------------------------------

def _expected_loadout(forge, spec, level, title):
    """What the builder gives for the spec once the server's class-mod character default is applied."""
    requests, notes = [], []
    for i, entry in enumerate(spec):
        entry = dict(entry)
        if not entry.get("serial") and entry.get("type") == "classmod" and not entry.get("character"):
            entry["character"] = forge.config.character
            notes.append("requests[%d]: class mod search without a character; using %s (config)"
                         % (i, forge.config.character))
        requests.append(LoadoutRequest.from_dict(entry))
    loadout = forge.builder.build(requests, level=level, title=title)
    return dataclasses.replace(loadout, warnings=tuple(loadout.warnings) + tuple(notes)), notes


@pytest.mark.parametrize("name", list(README_EXAMPLES))
def test_build_readme_examples_equal_builder(web, forge, name):
    spec = README_EXAMPLES[name]
    r = web.post("/api/build", {"requests": spec, "level": 60, "title": name})
    assert r.status == 200, r.text[:300]
    body = r.json
    assert set(body) == {"loadout", "html", "text"}
    expected, notes = _expected_loadout(forge, spec, 60, name)
    lo = body["loadout"]
    assert set(lo) == {"title", "level", "groups", "unmatched", "warnings", "items"}
    assert lo["title"] == name and lo["level"] == 60 and lo["unmatched"] == []
    assert lo["groups"] == list(expected.groups)
    assert lo["warnings"] == list(expected.warnings)
    assert [i["serial"] for i in lo["items"]] == [i.serial for i in expected.items]
    assert len(lo["items"]) >= len(spec)
    fields = {f.name for f in dataclasses.fields(LoadoutItem)}
    for got, want in zip(lo["items"], expected.items):
        assert set(got) == fields | {"shown_name"}
        assert got["shown_name"] == want.shown_name
        assert got == rt(dict(dataclasses.asdict(want), shown_name=want.shown_name))
        assert got["level"] == 60 and forge.codec.get_level(forge.codec.decode(got["serial"])) == 60
    for item in lo["items"]:
        assert htmllib.escape(item["serial"]) in body["html"], item["serial"]
        assert item["serial"] in body["text"]
    assert body["html"] == forge.render.html(expected) and body["text"] == forge.render.text(expected)
    assert body["html"].lstrip().lower().startswith("<!doctype html") and name in htmllib.unescape(body["html"])
    assert bool(notes) == any("class mod search" in w for w in lo["warnings"])


def test_build_without_level_does_not_relevel(web, forge):
    r = web.post("/api/build", {"requests": [{"type": "shield"}]})
    assert r.status == 200
    lo = r.json["loadout"]
    assert lo["level"] is None and lo["title"] == "Break Free Loadout"
    assert [i["serial"] for i in lo["items"]] == [
        i.serial for i in forge.builder.build([LoadoutRequest(type="shield")], level=None).items]
    assert lo["items"][0]["level"] == 50


def test_build_explicit_serials_skip_search(web, forge, serials):
    spec = [{"serial": serials["shotgun"], "group": "A", "display_name": "My Anarchy", "note": "hi <em>there</em>"},
            {"serial": serials["shield"], "group": "B"}, {"serial": serials["classmod"], "group": "B"}]
    r = web.post("/api/build", {"requests": spec, "level": 60, "title": "tray"})
    assert r.status == 200
    lo = r.json["loadout"]
    assert [i["serial"] for i in lo["items"]] == [forge.ops.relevel(s, 60) for s in
                                                  (serials["shotgun"], serials["shield"], serials["classmod"])]
    assert lo["groups"] == ["A", "B"] and lo["warnings"] == []          # no class-mod default for explicit serials
    assert lo["items"][0]["shown_name"] == "My Anarchy" and lo["items"][0]["note"] == "hi <em>there</em>"
    order = web.post("/api/build", {"requests": list(reversed(spec)), "level": 60}).json["loadout"]["items"]
    assert [i["serial"] for i in order] == [i["serial"] for i in reversed(lo["items"])]


def test_build_count_and_unmatched(web):
    r = web.post("/api/build", {"requests": [{"type": "shield", "count": 3}, {"query": "zzzz-no-such-item"}], "level": 60})
    assert r.status == 200
    lo = r.json["loadout"]
    assert len(lo["items"]) == 3 and len({i["serial"] for i in lo["items"]}) == 3
    assert len(lo["unmatched"]) == 1 and "zzzz-no-such-item" in lo["unmatched"][0]


def test_build_nothing_resolved_is_still_a_sheet(web):
    r = web.post("/api/build", {"requests": [{"query": "zzzz-no-such-item"}], "level": 60})
    assert r.status == 200 and r.json["loadout"]["items"] == [] and r.json["loadout"]["unmatched"]
    assert "No items" in r.json["html"]


def test_build_garbage_explicit_serial_is_an_item_warning(web):
    r = web.post("/api/build", {"requests": [{"serial": "garbage"}], "level": 60})
    assert r.status == 200
    item = r.json["loadout"]["items"][0]
    assert item["serial"] == "garbage" and item["warnings"]            # builder semantics: reported, not hidden


def test_build_unknown_keys_become_warnings(web):
    r = web.post("/api/build", {"requests": [{"type": "shield", "colour": "red"}]})
    assert r.status == 200
    assert any("colour" in w for w in r.json["loadout"]["warnings"])


@pytest.mark.parametrize("body", [
    {}, {"requests": []}, {"requests": {}}, {"requests": "shield"}, {"requests": [1]}, {"requests": ["shield"]},
    {"requests": [{}]}, {"requests": [{"count": 2}]}, {"requests": [{"type": 7}]},
    {"requests": [{"type": "shield", "count": 0}]}, {"requests": [{"type": "shield", "count": "2"}]},
    {"requests": [{"type": "shield", "count": True}]}, {"requests": [{"type": "shield", "count": 10 ** 9}]},
    {"requests": [{"type": "shield", "element": "plasma"}]},
    {"requests": [{"serial": 5}]}, {"requests": [{"type": "shield"}], "level": 0},
    {"requests": [{"type": "shield"}], "level": "60"}, {"requests": [{"type": "shield"}], "title": 5},
    {"requests": [{"type": "shield"}], "title": "x" * 201},
    {"requests": [{"type": "shield"}] * 201},
])
def test_build_bad_requests(web, body):
    assert_error(web.post("/api/build", body), 400, "bad_request")


def test_build_error_names_the_request(web):
    err = assert_error(web.post("/api/build", {"requests": [{"type": "shield"}, {"count": 2}]}), 400, "bad_request")
    assert "requests[1]" in err["message"]


# ---- errors, methods, framing --------------------------------------------------------------------------------

def test_bad_json(web):
    for raw in (b"{not json", b"", b"[1,2]", b"\"text\"", b"null", b"42", b"\xff\xfe\x00bad utf8",
                b"[" * 100000, b'{"serial": "x"} trailing'):
        assert_error(web.post("/api/identify", raw=raw, headers=JSON_CT), 400, "bad_request")


def test_content_type_is_enforced(web, serials):
    body = json.dumps({"serial": serials["shield"]}).encode()
    for ctype in (None, "text/plain", "application/x-www-form-urlencoded", "application/jsonx", "text/json", ""):
        headers = {"Content-Type": ctype} if ctype is not None else {}
        assert_error(web.post("/api/identify", raw=body, headers=headers), 415, "bad_request", "application/json")
    for ctype in ("application/json", "application/json; charset=utf-8", "Application/JSON;charset=UTF-8"):
        assert web.post("/api/identify", raw=body, headers={"Content-Type": ctype}).status == 200


def test_oversize_body_is_413(web):
    assert_error(web.post("/api/identify", raw=b"x" * (MAX_BODY + 1), headers=JSON_CT), 413, "bad_request")
    assert_error(web.post("/api/build", raw=b"y" * (3 * MAX_BODY), headers=JSON_CT), 413, "bad_request")
    # exactly at the limit is read and judged on its content
    pad = MAX_BODY - len(b'{"serial":""}')
    exact = b'{"serial":"' + b"x" * pad + b'"}'
    assert len(exact) == MAX_BODY
    assert_error(web.post("/api/identify", raw=exact, headers=JSON_CT), 400, "serial_error")


def test_oversize_declared_length_without_sending_it(web):
    r = web.raw_socket(b"POST /api/identify HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
                       b"Content-Length: 99999999999\r\nConnection: close\r\n\r\n")
    assert_error(r, 413, "bad_request")


def test_bad_framing(web):
    chunked = (b"POST /api/identify HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
               b"Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n2\r\n{}\r\n0\r\n\r\n")
    assert_error(web.raw_socket(chunked), 400, "bad_request")
    bad_len = (b"POST /api/identify HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
               b"Content-Length: banana\r\nConnection: close\r\n\r\n")
    assert_error(web.raw_socket(bad_len), 400, "bad_request")
    short = (b"POST /api/identify HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
             b"Content-Length: 50\r\nConnection: close\r\n\r\n{}")
    # the client half-closes after sending less than it promised
    with socket.create_connection(("127.0.0.1", web.port), timeout=20) as s:
        s.sendall(short)
        s.shutdown(socket.SHUT_WR)
        assert b" 400 " in s.recv(65536).split(b"\r\n")[0]
    no_length = (b"POST /api/identify HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
                 b"Connection: close\r\n\r\n")
    assert_error(web.raw_socket(no_length), 400, "bad_request", "Content-Length")


def test_malformed_request_line_is_json_error(web):
    r = web.raw_socket(b"GARBAGE\r\n\r\n")
    assert r.status == 400 and r.json["error"]["code"] == "bad_request"
    r = web.raw_socket(b"FOO /api/meta HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
    assert_error(r, 405, "bad_request")
    r = web.raw_socket(b"GET /" + b"a" * 70000 + b" HTTP/1.1\r\nHost: localhost\r\n\r\n")
    assert r.status == 414 and r.json["error"]["code"] == "bad_request"


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
@pytest.mark.parametrize("path", ["/api/identify", "/api/transform", "/api/diff", "/api/build"])
def test_post_endpoints_reject_other_methods(web, method, path):
    r = web.request(method, path)
    assert r.status == 405 and r.header("allow") == "POST"
    if method != "HEAD":
        assert_error(r, 405, "bad_request")
    else:
        assert r.body == b""


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@pytest.mark.parametrize("path", ["/api/meta", "/api/health", "/api/stats", "/api/search"])
def test_get_endpoints_reject_other_methods(web, method, path):
    r = web.request(method, path, body={"x": 1} if method in ("POST", "PUT", "PATCH") else None)
    assert_error(r, 405, "bad_request")
    assert r.header("allow") == "GET, HEAD"


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
def test_static_paths_reject_other_methods(web, method):
    r = web.request(method, "/")
    assert_error(r, 405, "bad_request")
    assert r.header("allow") == "GET, HEAD"


def test_head_on_api_has_length_and_no_body(web):
    r = web.request("HEAD", "/api/meta")
    full = web.get("/api/meta")
    assert r.status == 200 and r.body == b"" and int(r.header("content-length")) == len(full.body)


@pytest.mark.parametrize("path", ["/api", "/api/", "/api/nope", "/api/meta/", "/api/meta/extra", "/api/search/x",
                                  "/api/../etc/passwd", "/api%2fmeta", "/api%2Fidentify", "/api/%6deta"])
def test_unknown_api_paths_are_404_json(web, path):
    for method in ("GET", "POST"):
        r = web.request(method, path, body={} if method == "POST" else None)
        assert_error(r, 404, "not_found")


def test_error_responses_have_no_cors_and_are_not_cached(web, serials):
    responses = [web.get("/api/meta"), web.get("/api/nope"), web.post("/api/identify", {}), web.request("OPTIONS", "/api/meta"),
                 web.get("/api/search?limit=0"), web.get("/"), web.get("/api/meta", headers={"Origin": "http://localhost:5173"})]
    for r in responses:
        assert not [h for h in r.headers if h.startswith("access-control-")], r.headers
        assert r.header("x-content-type-options") == "nosniff"
    for r in responses[:5]:
        assert r.header("cache-control") == "no-store"


def test_preflight_gets_no_cors_blessing(web):
    r = web.request("OPTIONS", "/api/identify", headers={
        "Origin": "http://evil.example", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    assert r.status in (400, 405) and "access-control-allow-origin" not in r.headers


# ---- Host / Origin guard ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("host", ["localhost", "localhost:8734", "127.0.0.1", "127.0.0.1:1", "[::1]", "[::1]:65535",
                                  "LocalHost:80", "LOCALHOST"])
def test_good_hosts(web, host):
    assert web.get("/api/meta", headers={"Host": host}).status == 200
    assert web.get("/", headers={"Host": host}).status == 200
    assert host_allowed(host)


@pytest.mark.parametrize("host", ["evil.com", "evil.com:8734", "localhost.evil.com", "127.0.0.1.evil.com", "10.0.0.5",
                                  "192.0.2.5:8734", "0.0.0.0", "127.0.0.2", "[::2]", "localhost:", "localhost:99999x",
                                  "localhost@evil.com", "evil.com#localhost", "localhost evil", "", "localhost.", "::1",
                                  "[::1", "lo\tcalhost"])
def test_bad_hosts_are_rejected_everywhere(web, host, serials):
    for r in (web.get("/api/meta", headers={"Host": host}), web.get("/", headers={"Host": host}),
              web.get("/some/route", headers={"Host": host}),
              web.post("/api/identify", {"serial": serials["shield"]}, headers={"Host": host})):
        assert_error(r, 400, "bad_request", "host")
    assert not host_allowed(host)


def test_missing_and_duplicate_host_headers_are_rejected(web):
    assert_error(web.raw_socket(b"GET /api/meta HTTP/1.0\r\n\r\n"), 400, "bad_request", "host")
    assert_error(web.raw_socket(b"GET /api/meta HTTP/1.1\r\nHost: localhost\r\nHost: evil.com\r\n"
                                b"Connection: close\r\n\r\n"), 400, "bad_request", "host")
    assert_error(web.raw_socket(b"GET /api/meta HTTP/1.1\r\nHost: evil.com\r\nHost: localhost\r\n"
                                b"Connection: close\r\n\r\n"), 400, "bad_request", "host")


def test_absolute_form_request_still_needs_a_good_host(web):
    ok = web.raw_socket(b"GET http://evil.com/api/meta HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
    assert ok.status == 200                              # the Host header is what is judged
    bad = web.raw_socket(b"GET http://localhost/api/meta HTTP/1.1\r\nHost: evil.com\r\nConnection: close\r\n\r\n")
    assert_error(bad, 400, "bad_request", "host")


def test_cross_origin_requests_are_rejected(web, serials):
    for origin in ("http://evil.example", "https://evil.example:8734", "http://localhost.evil.example", "null"):
        assert_error(web.get("/api/meta", headers={"Origin": origin}), 400, "bad_request", "cross-origin")
        assert_error(web.post("/api/identify", {"serial": serials["shield"]}, headers={"Origin": origin}),
                     400, "bad_request", "cross-origin")
    for origin in ("http://localhost:5173", "http://127.0.0.1:8734", "http://[::1]:8734"):
        assert web.get("/api/meta", headers={"Origin": origin}).status == 200


# ---- internal errors never leak ----------------------------------------------------------------------------------

def test_unexpected_exception_is_a_clean_500(web, forge, serials, monkeypatch, capfd):
    def boom(serial):
        raise RuntimeError("secret internal detail /home/x/y.py line 3")
    monkeypatch.setattr(forge.ops, "describe", boom)
    r = web.post("/api/identify", {"serial": serials["shield"]})
    err = assert_error(r, 500, "internal")
    assert "secret internal detail" not in r.text and "RuntimeError" in err["message"]
    assert "secret internal detail" in capfd.readouterr().err               # ... but the server log has it
    assert web.get("/api/meta").status == 200                              # and the server carries on


def test_data_missing_is_503(tmp_path, config):
    forge = Forge.build(dataclasses.replace(config, data_dir=tmp_path / "no-such-data"))
    with running(forge) as web:
        err = assert_error(web.get("/api/search?type=shield"), 503, "data_missing")
        assert "missing" in err["message"]
        assert_error(web.get("/api/stats"), 503, "data_missing")
        assert web.get("/api/meta").json["catalog_count"] is None
        assert web.get("/api/health").status == 200 and web.get("/api/health").json["ok"] is False
        assert web.post("/api/diff", {"a": "garbage", "b": "x"}).status == 400


# ---- degraded and failed modules ----------------------------------------------------------------------------------

class BrokenRender(Module):
    name, purpose, requires, port = "render", "fails to start, on purpose", (), RenderPort

    def __init__(self, ctx):
        raise RuntimeError("render exploded on purpose")


class BrokenOps(Module):
    name, purpose, requires, port = "ops", "fails to start, on purpose", ("codec", "data", "rules"), OpsPort

    def __init__(self, ctx):
        raise RuntimeError("ops exploded on purpose")


def test_failed_module_is_503_naming_it_while_others_work(config, serials):
    forge = Forge.build(config, overrides={"render": BrokenRender})
    assert forge.states["render"].state == "failed"
    with running(forge) as web:
        err = assert_error(web.post("/api/build", {"requests": [{"type": "shield"}], "level": 60}),
                           503, "module_unavailable", "render")
        assert err["module"] == "render" and "'render'" in err["message"]
        # everything that does not need the render module still works
        assert web.get("/api/meta").status == 200
        assert web.get("/api/search?type=shield&limit=2").json["count"] == 2
        assert web.post("/api/identify", {"serial": serials["shield"]}).status == 200
        assert web.post("/api/transform", {"serial": serials["shotgun"], "op": "relevel", "level": 55}).status == 200
        assert web.post("/api/diff", {"a": serials["shield"], "b": serials["shotgun"]}).status == 200
        assert web.get("/api/stats").status == 200
        # request validation still comes first
        assert_error(web.post("/api/build", {"requests": []}), 400, "bad_request")
        health = web.get("/api/health").json
        assert health["ok"] is False
        assert {m["name"]: m["state"] for m in health["modules"]}["render"] == "failed"


def test_blocked_dependents_are_503_naming_the_module(config, serials):
    forge = Forge.build(config, overrides={"ops": BrokenOps})
    assert forge.states["ops"].state == "failed"
    assert forge.states["catalog"].state == "blocked" and forge.states["builder"].state == "blocked"
    with running(forge) as web:
        assert_error(web.post("/api/identify", {"serial": serials["shield"]}), 503, "module_unavailable", "ops")
        assert_error(web.post("/api/diff", {"a": "a", "b": "b"}), 503, "module_unavailable", "ops")
        assert_error(web.post("/api/transform", {"serial": serials["shield"], "op": "relevel", "level": 5}),
                     503, "module_unavailable", "ops")
        err = assert_error(web.get("/api/search?type=shield"), 503, "module_unavailable", "catalog")
        assert err["module"] == "catalog" and "ops" in err["message"]
        assert_error(web.get("/api/stats"), 503, "module_unavailable", "catalog")
        err = assert_error(web.post("/api/build", {"requests": [{"type": "shield"}]}), 503, "module_unavailable", "builder")
        assert err["module"] == "builder"
        # still alive: meta (with nulls), health, static
        meta = web.get("/api/meta")
        assert meta.status == 200 and meta.json["catalog_count"] is None
        assert meta.json["manifest_version"] == forge.data.manifest_version()
        health = web.get("/api/health").json
        states = {m["name"]: m["state"] for m in health["modules"]}
        assert health["ok"] is False and states["ops"] == "failed" and states["catalog"] == "blocked"
        assert web.get("/").status == 200


def test_degraded_module_still_serves(config, forge):
    from bl4forge.modules.render import MODULE as RealRender

    class SickRender(RealRender):
        def health(self):
            return HealthReport(ok=False, summary="sick on purpose")

    sick = Forge.build(config, overrides={"render": SickRender})
    assert sick.states["render"].state == "degraded"
    with running(sick) as web:
        r = web.post("/api/build", {"requests": [{"type": "shield"}], "level": 60})
        assert r.status == 200 and r.json["html"]
        health = web.get("/api/health").json
        assert health["ok"] is False
        assert {m["name"]: m["state"] for m in health["modules"]}["render"] == "degraded"


def test_forge_built_with_only_some_modules(config):
    partial = Forge.build(config, only=["codec", "data", "rules", "ops"])
    with running(partial) as web:
        assert web.get("/api/meta").json["catalog_count"] is None
        assert_error(web.get("/api/search?type=shield"), 503, "module_unavailable", "catalog")
        assert_error(web.post("/api/build", {"requests": [{"type": "shield"}]}), 503, "module_unavailable", "builder")
        assert web.get("/api/health").status == 200


# ---- static files ----------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def static_site(tmp_path_factory, forge):
    base = tmp_path_factory.mktemp("site")
    root = base / "static"
    (root / "assets").mkdir(parents=True)
    (root / "sub").mkdir()
    (root / "index.html").write_text("<!doctype html><title>ui</title><div id=root></div>", encoding="utf-8")
    (root / "assets" / "index-AbCd1234.js").write_text("console.log(1)", encoding="utf-8")
    (root / "assets" / "index-AbCd1234.css").write_text("body{}", encoding="utf-8")
    (root / "assets" / "plain.txt").write_text("plain", encoding="utf-8")
    (root / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (root / "sub" / "index.html").write_text("sub index", encoding="utf-8")
    (root / "vendor.5f3a9c21.js").write_text("v", encoding="utf-8")
    for name in ("a.json", "a.map", "a.woff2", "a.woff", "a.ttf", "a.png", "a.jpg", "a.ico", "a.wasm", "a.webmanifest",
                 "a.txt", "a.mjs", "a.gif", "a.webp", "a.unknownext", "A.JS"):
        (root / name).write_bytes(b"x")
    (root / ".secret-dotfile").write_text("DOTFILE SECRET", encoding="utf-8")
    (base / "secret.txt").write_text("TOP SECRET OUTSIDE", encoding="utf-8")
    (base / "static-evil").mkdir()
    (base / "static-evil" / "x.txt").write_text("SIBLING SECRET", encoding="utf-8")
    link = None
    try:
        os.symlink(base / "secret.txt", root / "link-out.txt")
        os.symlink(base, root / "dir-out")
        link = True
    except (OSError, NotImplementedError):
        link = False
    with running(forge, static_dir=root) as client:
        client.has_symlinks = link
        client.root = root
        yield client


def test_default_static_dir_serves_something(web):
    r = web.get("/")
    assert r.status == 200 and r.header("content-type") == "text/html; charset=utf-8" and b"<html" in r.body.lower()
    deep = web.get("/loadout/123/anything")
    assert deep.status == 200 and deep.body == r.body


def test_static_index_and_spa_fallback(static_site):
    index = (static_site.root / "index.html").read_bytes()
    for path in ("/", "/index.html", "/loadouts", "/loadouts/42", "/a/b/c/d", "/assets/", "/assets", "/sub", "/missing.html",
                 "/assets/not-built-yet-AAAAAAAA.js", "/?x=1", "/#frag", "/%E2%9C%93", "/ spaces", "//", "/./", "/a//b"):
        r = static_site.get(path.replace(" ", "%20"))
        assert r.status == 200, path
        assert r.body == index, path
        assert r.header("content-type") == "text/html; charset=utf-8"
        assert r.header("cache-control") == "no-cache"


def test_static_files_mime_and_cache_headers(static_site):
    cases = {
        "/assets/index-AbCd1234.js": ("text/javascript; charset=utf-8", "public, max-age=31536000, immutable"),
        "/assets/index-AbCd1234.css": ("text/css; charset=utf-8", "public, max-age=31536000, immutable"),
        "/vendor.5f3a9c21.js": ("text/javascript; charset=utf-8", "public, max-age=31536000, immutable"),
        "/assets/plain.txt": ("text/plain; charset=utf-8", "public, max-age=31536000, immutable"),
        "/favicon.svg": ("image/svg+xml", "no-cache"),
        "/sub/index.html": ("text/html; charset=utf-8", "no-cache"),
        "/a.json": ("application/json; charset=utf-8", "no-cache"),
        "/a.map": ("application/json; charset=utf-8", "no-cache"),
        "/a.woff2": ("font/woff2", "no-cache"), "/a.woff": ("font/woff", "no-cache"), "/a.ttf": ("font/ttf", "no-cache"),
        "/a.png": ("image/png", "no-cache"), "/a.jpg": ("image/jpeg", "no-cache"), "/a.gif": ("image/gif", "no-cache"),
        "/a.webp": ("image/webp", "no-cache"), "/a.ico": ("image/x-icon", "no-cache"),
        "/a.wasm": ("application/wasm", "no-cache"), "/a.mjs": ("text/javascript; charset=utf-8", "no-cache"),
        "/a.webmanifest": ("application/manifest+json; charset=utf-8", "no-cache"),
        "/a.txt": ("text/plain; charset=utf-8", "no-cache"), "/A.JS": ("text/javascript; charset=utf-8", "no-cache"),
        "/a.unknownext": ("application/octet-stream", "no-cache"),
    }
    for path, (ctype, cache) in cases.items():
        r = static_site.get(path)
        assert r.status == 200, path
        assert r.header("content-type") == ctype, path
        assert r.header("cache-control") == cache, path
        assert r.header("x-content-type-options") == "nosniff"
        assert int(r.header("content-length")) == len(r.body) > 0
        assert r.header("etag") and r.header("last-modified")
    assert static_site.get("/assets/index-AbCd1234.js").body == b"console.log(1)"
    assert not [h for h in static_site.get("/").headers if h.startswith("access-control-")]


def test_static_conditional_get_and_head(static_site):
    first = static_site.get("/assets/index-AbCd1234.js")
    again = static_site.get("/assets/index-AbCd1234.js", headers={"If-None-Match": first.header("etag")})
    assert again.status == 304 and again.body == b"" and again.header("etag") == first.header("etag")
    assert again.header("cache-control") == first.header("cache-control")
    other = static_site.get("/assets/index-AbCd1234.js", headers={"If-None-Match": 'W/"nope"'})
    assert other.status == 200 and other.body == first.body
    head = static_site.request("HEAD", "/assets/index-AbCd1234.js")
    assert head.status == 200 and head.body == b"" and int(head.header("content-length")) == len(first.body)
    assert head.header("content-type") == first.header("content-type")
    idx = static_site.get("/")
    assert static_site.get("/", headers={"If-None-Match": idx.header("etag")}).status == 304


TRAVERSAL = [
    "/..%2fsecret.txt", "/..%2f..%2fsecret.txt", "/..%2F..%2F..%2F..%2Fetc%2Fpasswd", "/%2e%2e/secret.txt",
    "/%2e%2e%2fsecret.txt", "/%2E%2E/%2E%2E/secret.txt", "/../secret.txt", "/../../secret.txt", "/static/../../secret.txt",
    "/static/../../pyproject.toml", "/assets/../../secret.txt", "/assets/..%2f..%2fsecret.txt", "/assets/../..%2fsecret.txt",
    "/..%5csecret.txt", "/..\\secret.txt", "/assets/..%5c..%5csecret.txt", "/%2e%2e%5csecret.txt",
    "/C:/Windows/win.ini", "/C%3A/Windows/win.ini", "/c:secret.txt", "/assets/C:/x", "/%00", "/index.html%00.png",
    "/a%00b", "/.secret-dotfile", "/assets/.secret-dotfile", "/.git/config", "/.env", "/%2esecret",
    "/static-evil/x.txt/../../secret.txt", "/..;/secret.txt", "/%252e%252e/secret.txt", "/assets/%2e%2e/%2e%2e/secret.txt",
    "/\x01", "/%01x", "/%7f",
]


@pytest.mark.parametrize("path", TRAVERSAL)
def test_static_never_leaves_its_directory(static_site, path):
    try:
        r = static_site.get(path)
    except (http.client.InvalidURL, ValueError):
        return                                           # the client itself refuses control characters
    for secret in (b"TOP SECRET", b"SIBLING SECRET", b"DOTFILE SECRET", b"root:", b"[fonts]", b"[core]"):
        assert secret not in r.body, (path, r.body[:80])
    assert r.status in (200, 404), (path, r.status)
    if r.status == 200:                                 # allowed only as the SPA page (e.g. %252e is a literal name)
        assert r.body == (static_site.root / "index.html").read_bytes(), path


@pytest.mark.parametrize("path", [
    "/..%2fsecret.txt", "/%2e%2e/secret.txt", "/static/../../pyproject.toml", "/../../secret.txt", "/..%5csecret.txt",
    "/C:/Windows/win.ini", "/%00", "/.secret-dotfile", "/assets/..%2f..%2fsecret.txt",
])
def test_static_traversal_is_404_not_the_spa(static_site, path):
    assert_error(static_site.get(path), 404, "not_found")


def test_static_symlinks_cannot_escape(static_site):
    if not static_site.has_symlinks:
        pytest.skip("symlinks not available")
    for path in ("/link-out.txt", "/dir-out/secret.txt"):
        r = static_site.get(path)
        assert b"TOP SECRET" not in r.body
        assert_error(r, 404, "not_found")


def test_static_api_lookalikes_never_fall_back(static_site):
    for path in ("/api%2fmeta", "/api%2F", "/api%2fnothing/x"):
        assert_error(static_site.get(path), 404, "not_found")


def test_static_without_a_build_is_a_404_json(forge, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with running(forge, static_dir=empty) as web:
        err = assert_error(web.get("/"), 404, "not_found", "not been built")
        assert_error(web.get("/some/route"), 404, "not_found")
        assert web.get("/api/meta").status == 200
    with running(forge, static_dir=tmp_path / "does-not-exist") as web:
        assert_error(web.get("/"), 404, "not_found")
        assert web.get("/api/health").status == 200


def test_static_index_is_reread_not_cached_by_the_server(forge, tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    (root / "index.html").write_text("one", encoding="utf-8")
    with running(forge, static_dir=root) as web:
        assert web.get("/").text == "one"
        (root / "index.html").write_text("two!", encoding="utf-8")
        assert web.get("/").text == "two!"


# ---- connections ---------------------------------------------------------------------------------------------------

def test_keep_alive_survives_errors_and_unread_bodies(web, serials):
    conn = http.client.HTTPConnection("127.0.0.1", web.port, timeout=20)
    try:
        body = json.dumps({"serial": serials["shield"]})
        steps = [
            ("POST", "/api/meta", body, JSON_CT, 405),                       # body never read by a handler
            ("POST", "/api/identify", body, {"Content-Type": "text/plain"}, 415),
            ("POST", "/api/identify", "x" * (MAX_BODY + 10), JSON_CT, 413),
            ("GET", "/api/search?limit=0", None, {}, 400),
            ("POST", "/api/identify", body, JSON_CT, 200),
            ("GET", "/api/nope", None, {}, 404),
            ("GET", "/", None, {}, 200),
            ("POST", "/api/identify", "{", JSON_CT, 400),
            ("POST", "/api/identify", body, JSON_CT, 200),
        ]
        for method, path, data, headers, status in steps:
            conn.request(method, path, body=data, headers=headers)
            r = conn.getresponse()
            r.read()
            assert r.status == status, (method, path, r.status)
    finally:
        conn.close()


def test_idle_client_does_not_block_others(web):
    idle = socket.create_connection(("127.0.0.1", web.port), timeout=5)
    try:
        assert web.get("/api/meta").status == 200            # a silent connection holds one thread, not the server
    finally:
        idle.close()


def test_concurrent_requests_match_serial_results(config):
    """20 parallel searches (plus a mix of other calls) on a COLD forge, so the catalog's per-serial memo
    is filled by many threads at once; every answer must equal the single-threaded one."""
    cold = Forge.build(config)
    params = [SEARCHES[i % 6] for i in range(20)]
    expected = [[e.serial for e in cold.catalog.search(SearchQuery(**p)).entries] for p in params]
    fresh = Forge.build(config)
    with running(fresh) as web:
        sample = fresh.catalog.search(SearchQuery(type="shotgun", limit=1)).entries[0].serial
        ident = rt(fresh.ops.describe(sample).to_dict())

        def one(i):
            r = web.get("/api/search?" + _qs(params[i]))
            return r.status, [x["serial"] for x in r.json["results"]]

        def other(i):
            if i % 3 == 0:
                r = web.post("/api/identify", {"serial": sample})
                return r.status, r.json["info"]
            if i % 3 == 1:
                r = web.post("/api/build", {"requests": [{"type": "shield", "count": 2}], "level": 60})
                return r.status, len(r.json["loadout"]["items"])
            r = web.get("/api/health")
            return r.status, r.json["ok"]

        with ThreadPoolExecutor(max_workers=20) as pool:
            searches = [pool.submit(one, i) for i in range(20)]
            others = [pool.submit(other, i) for i in range(9)]
            got = [f.result(timeout=60) for f in searches]
            misc = [f.result(timeout=60) for f in others]
        assert [g[0] for g in got] == [200] * 20
        assert [g[1] for g in got] == expected
        assert all(m[0] == 200 for m in misc)
        assert misc[0][1] == ident and misc[1][1] == 2 and misc[2][1] is True


# ---- server lifecycle / cli ---------------------------------------------------------------------------------------------

def test_import_has_no_side_effects_and_cli_does_not_load_it():
    code = ("import sys; import bl4forge.cli; assert 'bl4forge.web' not in sys.modules; "
            "import bl4forge.web as w; assert callable(w.serve) and callable(w.create_server)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONPATH=str(ROOT / "src")), cwd=str(ROOT))
    assert r.returncode == 0, r.stderr
    assert r.stdout == "" and r.stderr == ""


def test_create_server_port_busy_raises_port_in_use(forge):
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    try:
        with pytest.raises(PortInUse) as exc:
            create_server(forge, port=port)
        assert str(port) in str(exc.value) and "in use" in str(exc.value)
    finally:
        holder.close()


def test_create_server_rejects_bad_port_and_host(forge):
    from bl4forge.web import ServerStartError
    with pytest.raises(ServerStartError):
        create_server(forge, port=70000)
    with pytest.raises(ServerStartError):
        create_server(forge, host="no-such-host.invalid", port=0)


def test_server_url_and_ipv6_loopback(forge):
    server = create_server(forge, host="127.0.0.1", port=0, quiet=True)
    try:
        assert server.url == "http://127.0.0.1:%d/" % server.server_address[1]
    finally:
        server.server_close()
    try:
        v6 = create_server(forge, host="::1", port=0, quiet=True)
    except Exception:
        pytest.skip("no IPv6 loopback here")
    try:
        assert v6.url.startswith("http://[::1]:")
        thread = threading.Thread(target=v6.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        conn = http.client.HTTPConnection("::1", v6.server_address[1], timeout=10)
        conn.request("GET", "/api/meta", headers={"Host": "[::1]:%d" % v6.server_address[1]})
        assert conn.getresponse().status == 200
        conn.close()
        v6.shutdown()
        thread.join(5)
    finally:
        v6.server_close()


def _stub_serve_forever(monkeypatch):
    """Make serve() return as if Ctrl+C arrived the moment the server started listening."""
    from bl4forge.web import WebServer

    def interrupted(self, poll_interval=0.5):
        raise KeyboardInterrupt
    monkeypatch.setattr(WebServer, "serve_forever", interrupted)


def test_serve_prints_url_opens_browser_and_stops_on_ctrl_c(forge, monkeypatch, capsys):
    import webbrowser
    from bl4forge.web import serve
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url))
    _stub_serve_forever(monkeypatch)
    assert serve(forge, port=0, open_browser=True, quiet=True) == 0
    out, err = capsys.readouterr()
    lines = out.splitlines()
    assert lines[0].startswith("bl4forge web UI: http://127.0.0.1:") and "Ctrl+C" in lines[0]
    assert opened == [lines[0].split()[3]] and lines[-1] == "stopped" and err == ""
    assert serve(forge, port=0, quiet=True) == 0 and len(opened) == 1          # no --open, no browser


def test_serve_warns_about_sick_modules_and_open_hosts(config, monkeypatch, capsys):
    from bl4forge.web import serve
    forge = Forge.build(config, overrides={"render": BrokenRender})
    _stub_serve_forever(monkeypatch)
    assert serve(forge, host="0.0.0.0", port=0, quiet=True) == 0
    err = capsys.readouterr().err
    assert "module 'render' is failed" in err and "503" in err and "doctor" in err
    assert "0.0.0.0" in err and "other machines" in err


def _cli(*args, **kw):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    env.pop("BL4FORGE_CONFIG", None)
    return subprocess.Popen([sys.executable, "-m", "bl4forge", *args], cwd=str(ROOT), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kw)


def test_serve_help_and_arguments():
    r = subprocess.run([sys.executable, "-m", "bl4forge", "serve", "--help"], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONPATH=str(ROOT / "src")), cwd=str(ROOT))
    assert r.returncode == 0
    for flag in ("--host", "--port", "--open", "--quiet"):
        assert flag in r.stdout
    for bad in (["--port", "99999"], ["--port", "http"], ["--port", "-1"]):
        r = subprocess.run([sys.executable, "-m", "bl4forge", "serve", *bad], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=str(ROOT / "src")), cwd=str(ROOT))
        assert r.returncode == 2 and "Traceback" not in r.stderr


def test_serve_port_busy_exits_4_with_a_clear_message():
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    try:
        proc = _cli("serve", "--port", str(port))
        out, err = proc.communicate(timeout=60)
    finally:
        holder.close()
    assert proc.returncode == 4, (out, err)
    assert err.startswith("error: ") and "already in use" in err and str(port) in err and "--port" in err
    assert "Traceback" not in err


def test_serve_runs_logs_and_stops_cleanly_on_ctrl_c():
    if sys.platform == "win32":
        pytest.skip("SIGINT delivery differs on Windows")
    proc = _cli("serve", "--port", "0")
    watchdog = threading.Timer(60, proc.kill)
    watchdog.start()
    try:
        line = proc.stdout.readline()
        assert line.startswith("bl4forge web UI: http://127.0.0.1:"), line
        url = line.split()[3]
        port = int(url.rstrip("/").rsplit(":", 1)[1])
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        conn.request("GET", "/api/meta")
        r = conn.getresponse()
        assert r.status == 200 and json.loads(r.read())["catalog_count"] == D.CATALOG_ROWS
        conn.request("GET", "/api/search?limit=0")
        assert conn.getresponse().read() and True
        conn.close()
        proc.send_signal(signal.SIGINT)
        out, err = proc.communicate(timeout=30)
    finally:
        watchdog.cancel()
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0, (out, err)
    assert "stopped" in out and "Traceback" not in err and "KeyboardInterrupt" not in err
    lines = [ln for ln in err.splitlines() if ln.startswith("GET ")]
    assert any(ln.startswith("GET /api/meta 200 ") and ln.endswith("ms") for ln in lines), err
    assert any(ln.startswith("GET /api/search?limit=0 400 ") for ln in lines), err


def test_serve_quiet_logs_nothing():
    if sys.platform == "win32":
        pytest.skip("SIGINT delivery differs on Windows")
    proc = _cli("serve", "--port", "0", "--quiet")
    watchdog = threading.Timer(60, proc.kill)
    watchdog.start()
    try:
        line = proc.stdout.readline()
        port = int(line.split()[3].rstrip("/").rsplit(":", 1)[1])
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        conn.request("GET", "/api/health")
        assert conn.getresponse().status == 200
        conn.close()
        proc.send_signal(signal.SIGINT)
        out, err = proc.communicate(timeout=30)
    finally:
        watchdog.cancel()
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0 and err.strip() == "", err
