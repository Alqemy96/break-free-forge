# CONTRACT - module `builder`

**Purpose:** Turn loadout requests into a verified, re-leveled Loadout.
**Requires:** catalog, ops
**Class:** `BuilderModule` in `src/bl4forge/modules/builder/__init__.py` (export it as `MODULE`; split into more files inside this directory as you like)
**Read first:** `docs/AGENT_RULES.md` (module rules; see also docs/runbooks/DEVELOPER.md), `docs/ARCHITECTURE.md`, the `BuilderPort` docstring in `core/ports.py`.
**Tests live in:** `tests/modules/test_builder*.py`

## Port to implement
`BuilderPort` in `core/ports.py`.

## Port from legacy
`legacy/skills/bl4-loadout/scripts/forge.py`: `enrich` (217-280) and the request-resolution loop inside `cmd_build` (631-708). The
JSON-to-request parsing is already `LoadoutRequest.from_dict` in `core/types.py` (CLI uses it).
`build()` returns a `Loadout` (items, groups in first-seen order, unmatched, warnings). `enrich`
returns a `LoadoutItem`: decoded rarity/element/name win over catalog hints with a warning when they
disagree ("database says X, the serial says Y - trusting the serial").

## Invariants
- `relevel_failure_is_a_warning`: force a re-level failure (e.g. override codec with a fake that raises) and assert the item carries a warning and the code is NOT presented as re-leveled.
- `level_mismatch_is_a_warning`: requested level != decoded level -> warning.
- `misses_are_unmatched`: an impossible query lands in `Loadout.unmatched`; nothing raises.
- `groups_keep_first_seen_order`.
- `count_gt_1_returns_variants`.
- `explicit_serial_entries_work`: a request with `serial` skips search.
- `matches_legacy`: build the three example loadouts from the plugin README (cryo loadout; Wombo Combo + Plasma Coil + cryo Super Soldier; level-60 radiation shotgun) and compare serials, levels and rarities to legacy `cmd_build` output.

## Health
Build a one-item loadout from a known query at level 60 and check level == 60.

Implemented as four checks, all through the module's own `build()` (so a sick neighbour makes the builder
DEGRADED, honestly): `one_item_at_60` (the 'anarchy' shotgun query at level 60 returns exactly the known
level-60 serial, level 60, no warnings, decoded name Anarchy, element impact, group kept, nothing unmatched),
`explicit_serial` (the stored level-50 code re-levels to the same known serial), `no_relevel_keeps_level`
(`level=None` leaves level 50 and `Loadout.level` None) and `miss_is_unmatched`. Never raises; about 3 ms.

## Deviations from legacy
Parity bar met (`tests/modules/test_builder.py`): the request-resolution loop of legacy `cmd_build` (legacy
`search` + `enrich`, run in process) and `builder.build` agree on serials, levels, decoded rarity / element /
name / category / parts / odds, **warnings (text and order)**, notes, groups, display names, manufacturer /
label / type / source, item order and group order, for the three README loadouts (a cryo loadout, Wombo Combo +
Plasma Coil + cryo Super Soldier, a level-60 radiation shotgun), 14 further specs (a class mod per character and
per alias, shield, repkit, grenade, enhancement, assault rifle, heavy + pistol, a `count=3` request, a name query
with `count=4`, misses mixed with hits, interleaved groups) and an explicit-serial spec, each at level 60 and
with no level (and 30 for the explicit one). `enrich` is also compared with legacy `enrich(row, 60)` for ALL
8,520 distinct serials of the database, and for every weapon whose database element the bitstream contradicts
(the warning text and the winner are identical). Differences, all deliberate:

**Shape**
- `build()` returns a `core.types.Loadout`; `enrich()` a frozen `LoadoutItem`, not a dict. Items are built
  from `CatalogEntry` rows; `group`, `note` and `display_name` are applied by `build()` (`enrich` leaves them
  empty). Legacy printed a JSON summary and wrote files; that is the cli's and render's job now.
- `element` is a vocab name (`shock`, not `electric` / `Shock`) or None. It is the DECODED element when the
  bitstream has one, else the catalog hint (gear has no element in the bitstream, so a shield keeps the
  database's label; this is what lets a "cryo Super Soldier" show Cryo). Legacy kept the raw label in `element`
  and the decoded one in `true_element`; they are one field now, the best truth. Visible consequence: a weapon
  whose database label is 'N/A' but whose serial has no element part is now Impact (legacy showed no badge).
- `rarity` is likewise `true_rarity or rarity`, `legendary_name` / `category` / `parts` (part labels) / `odds`
  (`ops.format_odds(ops.rarity_estimate(info))`) come from `ops.describe`, once per item. The level is the
  DECODED level, from `ops.describe(serial).level` (legacy: `codec.get_level(codec.decode(...))`).
- Re-leveling goes through `ops.relevel` (change request, resolved: option A); legacy called the codec.
- Explicit entries: the `LoadoutRequest` fields stand in for the catalog row exactly as in legacy
  (`name` default "Item", `label or type`, `bulletType` = the request's element). Legacy also read a
  `weaponType` key; `LoadoutRequest.from_dict` drops unknown keys, so `weapon_type` is "" for explicit
  entries. A pasted serial is trimmed of whitespace, wrapping quotes and a trailing comma (legacy: undecodable).
- `Loadout.level` is the level asked for (None = not re-leveled). `Loadout.title` is the argument.
  `Loadout.warnings` holds BUILD-level notices only (below); item warnings stay on their items (legacy's JSON
  summary merged them into one sorted list; the cli can do the same with `{w for i in items for w in i.warnings}`).
  Plain dicts in `requests` are accepted (parsed with `LoadoutRequest.from_dict`).

**Warnings**
- Same texts as legacy: `re-level to N failed (...) - code left at its stored level`, `decode failed: ...`,
  `requested level N but the code decodes as M`, `database says element X, the serial says Y - trusting the
  serial` (labels from `vocab.ELEMENT_LABELS`; the dash is the em dash legacy used), plus the decoded item's own
  warnings (`info.warnings`: unowned content, parts missing from the manifest).
- New: `database says rarity X, the serial says Y - trusting the serial` (case-insensitive; the shipped database
  never triggers it: the only rarity differences are 62 rows with no decoded rarity, where the hint stands).
  `odds lookup failed: ...` when the odds cannot be computed. A catalog or request element that is not a vocab
  element is ignored with a warning (`... is not a known element and was ignored`).
- Legacy wrapped describe + odds in one try ("part lookup failed"); now `ops.describe` raising is a
  `decode failed` warning (level None, hints stand) and the odds have their own warning. A failed re-level AND
  an undecodable serial give two warnings, like legacy. Without a manifest ops reports `manifest_ok=False` plus a
  warning, which is now shown on the item (legacy stayed silent); no decoded facts are claimed then.
- Level mismatch is reported even when the re-level raised (legacy did too: the stored level is not the
  requested one).

**Requests and misses**
- `Loadout.unmatched` names a miss by its query text (legacy: `query or json.dumps(request)`), else by a compact
  description of the search fields: `type=shotgun element=plasma rarity=common` (order: type, element,
  manufacturer, rarity, character). A group stays in `Loadout.groups` even when its requests all missed (legacy
  too; render skips empty groups).
- A request with neither `serial` nor any search field is NOT run (legacy returned the database's first row, an
  arbitrary item): it goes to `unmatched` as `(empty request)` with a build notice.
- `count < 1` (or not a number): legacy's `limit=0` happened to return one row; now the request asks for 1 and a
  notice says so. `count` is passed to the catalog as the limit; `include_unowned` stays False, `verify_element`
  True. A shortfall (`asked for 3, found 1`), matches hidden for unowned content (keys are pack IDS, as returned by
  the catalog; the cli maps them with `rules.pack_label` if it wants labels) and, when the request came up short,
  rows dropped because the database's element label disagreed with the serial, are reported as notices (legacy
  printed nothing).
- A search that raises (database missing, a sick neighbour) is a miss plus a notice naming the error; it never
  propagates. The query for a request is built from the request exactly as legacy did; unknown elements
  therefore miss (the catalog matches nothing for them).
- A level that is not a whole number: `Loadout.level` None, nothing re-leveled, one notice (`enrich` called with
  such a level warns on the item instead).
- No character default: legacy did not apply one either (SKILL.md tells the caller to pass `character`), so a
  class-mod request without `character` takes the first class mod in database order. The cli / skill should pass
  `config.character` for class mods.

**State**: none. The module holds no caches or globals; every call asks the neighbours afresh.

## Notes for callers (cli)
- `forge.builder.build(requests, level=None, title="Break Free Loadout")`; `requests` are
  `LoadoutRequest`s (`LoadoutRequest.from_dict` for JSON spec entries). The cli's `--level` default decides
  whether to pass `config.level` (60) or None; the builder itself never reads `config.level`.
- Never raises for data problems. Look at `Loadout.unmatched` (misses), `Loadout.warnings` (build notices) and
  each `item.warnings` (re-level / decode / disagreeing labels / unowned content). An empty `items` is legacy's
  "no items resolved" (exit 3): the cli decides what to do.
- `forge.builder.enrich(entry, level)` is the single-row version (e.g. `search --level`); it needs a
  `CatalogEntry` (`forge.catalog.find_by_serial` or a search result).
- `item.level` is what the code DECODES as; trust it, not the level you asked for. `item.serial` is the
  re-leveled code, or the stored one when the re-level failed.
- `describe_request(request)` (module-level helper in `bl4forge.modules.builder`) gives the text used in
  `unmatched` for a request.
