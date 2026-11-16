"""Capture realistic API-shaped fixtures for the UI's mock mode (VITE_MOCK=1).

Dev tool only. Payloads come from the web layer's own handlers (`bl4forge.web._api.Api`, the code
behind `bl4forge serve`), called in-process, so the mock answers exactly what the server answers.
Run from the project root:  PYTHONPATH=src python3 ui/scripts/capture_fixtures.py
Writes ui/src/mock/fixtures.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from bl4forge.core.config import Config
from bl4forge.core.forge import Forge
from bl4forge.web._api import Api, Fields

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "ui" / "src" / "mock" / "fixtures.json"

SEARCHES = [
    {"query": "anarchy"}, {"type": "shotgun", "limit": "12"}, {"type": "pistol", "limit": "10"},
    {"type": "smg", "limit": "10"}, {"type": "assault_rifle", "limit": "10"}, {"type": "sniper", "limit": "10"},
    {"type": "heavy", "limit": "8"}, {"type": "shield", "limit": "10"},
    {"type": "classmod", "character": "gravitar", "limit": "8"}, {"type": "classmod", "character": "paladin", "limit": "6"},
    {"type": "repkit", "limit": "8"}, {"type": "grenade", "limit": "8"}, {"type": "enhancement", "limit": "8"},
    {"query": "wombo"}, {"element": "cryo", "limit": "12"}, {"element": "shock", "limit": "8"},
    {"element": "corrosive", "limit": "8"}, {"element": "radiation", "limit": "8"}, {"element": "fire", "limit": "8"},
]


def main() -> int:
    forge = Forge.build(Config.load())
    web = Api(forge)
    level = forge.config.level

    def search(params):
        return web.search(Fields(dict(params, level=str(level)), from_query=True))

    pool = {}
    for params in SEARCHES:
        for row in search(params)["results"]:
            pool.setdefault(row["serial"], row)
    rows = list(pool.values())

    identify = {}
    for row in rows[:60]:
        try:
            identify[row["serial"]] = web.identify(Fields({"serial": row["serial"]}))
        except Exception:  # a sample that does not decode is simply left out
            pass

    weapon = next(r for r in rows if r["type"] == "weapon" and r["decoded"]["element"] == "cryo")
    shield = next(r for r in rows if r["type"] == "shield")
    cmod = next(r for r in rows if r["type"] == "classmod")
    for r in (weapon, shield, cmod):
        identify[r["serial"]] = web.identify(Fields({"serial": r["serial"]}))

    ws = weapon["serial"]
    cat = identify[ws]["info"]["category_id"]
    same = [s for s, p in identify.items() if s != ws and p["info"]["category_id"] == cat]
    t = lambda body: web.transform(Fields(dict(body, serial=ws)))
    transforms = {
        "relevel_50": t({"op": "relevel", "level": 50}),
        "set_element_fire": t({"op": "set_element", "element": "fire"}),
        "set_element_impact": t({"op": "set_element", "element": "impact"}),
        "reseed_1234": t({"op": "reseed", "seed": 1234}),
    }
    if same:
        transforms["swap_7_8"] = t({"op": "swap", "source": same[0], "positions": [7, 8], "allow_cross": False})
        transforms["swap_source"] = same[0]
    fire = transforms["set_element_fire"]["serial"]
    diff = {"a": ws, "b": fire, "rows": web.diff(Fields({"a": ws, "b": fire}))["rows"]}

    build = web.build(Fields({
        "title": "Cryo Gravitar", "level": level,
        "requests": [
            {"group": "Weapons", "serial": weapon["serial"], "display_name": "Ice Party", "name": weapon["name"], "label": weapon["label"]},
            {"group": "Gear", "serial": shield["serial"], "note": "keeps the <em>shield</em> up", "name": shield["name"], "label": shield["label"]},
            {"group": "Gear", "serial": cmod["serial"], "name": cmod["name"], "label": cmod["label"]},
        ],
    }))

    out = {"meta": web.meta(Fields({})), "health": web.health(Fields({})), "pool": rows, "identify": identify,
           "transforms": transforms, "diff": diff, "build": build, "stats": web.stats(Fields({}))}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote %s: %d pool rows, %d identify samples, %d transforms" % (OUT, len(rows), len(identify), len(transforms)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
