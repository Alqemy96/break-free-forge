# Web layer contract (server <-> UI)

The web layer is an OUTER layer like the cli: it consumes a `Forge`, contains no domain logic, and reaches modules
only through ports. `bl4forge serve` = Python stdlib `http.server` (ThreadingHTTPServer), JSON API under `/api`,
the built React bundle served from `src/bl4forge/web/static/` for everything else (SPA fallback to `index.html`).

Default bind `127.0.0.1:8734`. Private/local only: reject any request whose `Host` header is not
`localhost`/`127.0.0.1`/`[::1]` (DNS-rebinding guard), no CORS headers, POST bodies must be
`application/json` and <= 1 MB, static serving must not escape its directory. All JSON is UTF-8, snake_case,
tuples become arrays. The server builds ONE `Forge` at startup and reuses it.

## Errors
Any failure returns HTTP 400/404/405/413/415/500/503 with
`{"error": {"code": "<code>", "message": "<human sentence>"}}`. Codes: `bad_request`, `serial_error`,
`module_unavailable` (503), `data_missing` (503), `save_error` (400: wrong key, corrupt save, unknown slot, refused edit), `key_missing` (503: no `[save]` key in config.toml), `not_found`, `internal`. Never a traceback in the body.

## Endpoints

`GET /api/meta` ->
```
{"version": "...", "level": 60, "character": "gravitar", "owned_packs": ["coregame", ...],
 "catalog_count": 9875, "manifest_version": "2026-08-01 (...)",
 "elements": [{"id": "cryo", "label": "Cryo"}, ...],            // vocab.ELEMENTS
 "rarities": ["Common", ... "Vile"], "characters": ["gravitar", ...],
 "types": [{"id": "pistol", "label": "Pistol", "group": "weapon"}, ... "shield","classmod","repkit","grenade","enhancement"]}
```
`GET /api/health` -> `{"ok": bool, "modules": [ <rows from core.doctor.diagnose> ]}`
`GET /api/stats` -> `catalog.stats()` verbatim.

`GET /api/search?query=&type=&element=&manufacturer=&rarity=&character=&limit=25&include_unowned=0&verify_element=1&level=60`
(`level` optional: when present every returned serial is re-leveled with `ops.relevel`; limit 1..200) ->
```
{"count": 3, "level": 60,
 "results": [{"serial": "@U...", "name": "...", "type": "weapon", "weapon_type": "shotgun",
              "manufacturer": "Tediore", "label": "Tediore Shotgun", "rarity": "Legendary", "element": "cryo",
              "source": "...", "level": 60,
              "decoded": {"display_name": "...", "category": "...", "rarity": "...", "element": "cryo"|null,
                          "owned": true, "warnings": []}}],
 "hidden": [{"pack": "bounty_pack_3", "label": "Bounty Pack 3 - ...", "count": 26}],
 "dropped_element_mismatch": 0}
```
`decoded` comes from `ops.describe` (the bitstream is the truth; `rarity`/`element` outside `decoded` are catalog hints).

`POST /api/identify` `{"serial": "@U...", "level": 60?}` (level -> re-level first) ->
```
{"serial": "...", "info": <ItemInfo.to_dict()>, "odds": "<ops.format_odds(...)>",
 "parts": [{"position": 0, "token_index": 7, "label": "...", "category_id": 11, "index": 5, "raw": "...", "category_link": null}],
 "problems": [<rules.validate strings>], "is_weapon": true, "can_set_element": true}
```
`position` is the index into `ops.part_list` (what `swap` positions mean). `can_set_element` is true only for weapons.

`POST /api/transform`
`{"serial": "...", "op": "relevel", "level": 60}` |
`{"serial": "...", "op": "set_element", "element": "cryo"|"impact"}` (weapons only; else 400) |
`{"serial": "...", "op": "reseed", "seed": 123?}` (omit seed -> random 0..2^31-1) |
`{"serial": "...", "op": "swap", "source": "@U...", "positions": [3,4], "allow_cross": false}` ->
the same payload as `/api/identify` for the NEW serial, plus `"previous": "<old serial>"` and `"note": "<warnings, incl. 'passed structural checks only'>"`.

`POST /api/diff` `{"a": "...", "b": "..."}` -> `{"rows": [{"field": "...", "a": ..., "b": ...}]}`

`POST /api/build` `{"requests": [<LoadoutRequest fields: group, serial, query, type, element, manufacturer, rarity, character, count, note, display_name>],
"level": 60?, "title": "..."}` ->
```
{"loadout": {"title": "...", "level": 60, "groups": [...], "unmatched": [...], "warnings": [...],
             "items": [{<LoadoutItem fields>, "shown_name": "..."}]},
 "html": "<full self-contained sheet>", "text": "<plain list>"}
```
Omitted `level` means "do not re-level" (builder semantics). For class-mod search entries with no `character`, the SERVER
applies `config.character` and adds a warning (same rule as the cli). Explicit-serial requests skip search.
The UI's loadout tray is a list of explicit-serial requests, so rebuilding after reorder/regroup/remove is one call.

## Save files (stateless: bytes/text in, bytes/text out; the server never reads or writes save paths)
- `POST /api/save/open` `{"data_b64": "<.sav bytes>", "platform": "ps5"|"pc" (default ps5), "steam_id": "..." (pc only)}` ->
  `{"sha256", "platform", "yaml": "<text>", "summary": {name,class,difficulty,level,points,currencies,items},
  "items": [{ref,area,slot,serial,line,name,level,rarity,category,element,warnings,error}]}`. Names come from the ops cell;
  a serial that will not decode has `error` set instead of being dropped.
- `POST /api/save/items` `{"yaml": "..."}` -> `{"summary", "items"}`.
- `POST /api/save/apply` `{"yaml": "...", "edits": [{"op":"currency","name":"eridium","value":222} |
  {"op":"point_pool","name":"echotokenprogresspoints","value":1000} (profile saves) |
  {"op":"level","level":30,"points":123} | {"op":"serial","ref":"backpack/slot_0","serial":"@U..."}]}` ->
  `{"yaml": "<patched>", "changed_lines": [{"line","old","new"}], "summary"}`. Each edit changes exactly one existing line;
  a serial edit is refused (400 `serial_error`) unless the serial decodes.
- `POST /api/save/write` `{"yaml": "...", "platform", "steam_id"}` -> `{"data_b64","bytes","sha256","platform","verified":true}`
  (the re-wrapped save, proven to decrypt back to the same YAML). Save the bytes as a COPY; never over the original.

## Static
`GET /` and any non-`/api` path that is not a file -> `index.html`. Files from `src/bl4forge/web/static/`.
Cache: `index.html` no-cache; hashed assets `public, max-age=31536000, immutable`.

## CLI
`bl4forge serve [--host 127.0.0.1] [--port 8734] [--open] [--allow-remote]` (prints the URL; a non-loopback `--host` is refused unless `--allow-remote` is given, RISKY: no login; Ctrl+C exits cleanly; exit 4 if port busy
with a clear message). Added to `src/bl4forge/cli/` by the web-api author as a minimal additive edit.

---
## Implementation notes (authoritative where they differ from the text above)
Added by the web-api author, confirmed against the running server and the UI:
- `/api/search` also returns `"notes": [str]` (e.g. class-mod search defaulting to `config.character`). A failed re-level keeps the
  stored serial and adds a warning to `decoded.warnings`; each row's `level` is what its shown serial decodes as; top-level `level`
  is the requested level or `null`. Out-of-range `limit` (not 1..200) / `level` (not 1..100) and unknown `element` are 400, not clamped.
- `reseed` also returns `"seed"` (the seed used). A 503 `module_unavailable` also carries `error.module`.
- Every non-listed failure (405 + `Allow`, 413, 415, bad Host/Origin, malformed request) uses `code: "bad_request"` with the right
  HTTP status. `/api/meta` never returns 503: `catalog_count` / `manifest_version` are `null` if their module is down.
- `/api/build`: server notices (character default, ignored unknown keys) go to `loadout.warnings`; no-match returns 200 with the miss in
  `unmatched`; an explicit garbage serial returns 200 with an item warning; guardrails: <=200 requests, `count` 1..200, title <=200 chars.
- swap `note` always states structural-check status; it never says "valid in game".
- Static: anything escaping the static dir is a JSON 404; `assets/` and hashed names are immutable-cached, everything else `no-cache`;
  ETag/304 supported. Extra headers: nosniff, X-Frame-Options SAMEORIGIN, Referrer-Policy no-referrer, CORP same-origin.
- The Host check ignores the port (so a Vite dev proxy at localhost:5173 works); there is still no CORS.
