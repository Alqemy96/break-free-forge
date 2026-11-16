# CONTRACT - module `catalog`

**Purpose:** Search the community serial database, verified against the decoded bitstream and ownership.
**Requires:** codec, data, rules, ops
**Class:** `CatalogModule` in `src/bl4forge/modules/catalog/__init__.py` (export it as `MODULE`; split into more files inside this directory as you like)
**Read first:** `docs/AGENT_RULES.md` (module rules; see also docs/runbooks/DEVELOPER.md), `docs/ARCHITECTURE.md`, the `CatalogPort` docstring in `core/ports.py`.
**Tests live in:** `tests/modules/test_catalog*.py`

## Port to implement
`CatalogPort` in `core/ports.py`.

## Port from legacy
`legacy/skills/bl4-loadout/scripts/forge.py`: `load_db`, `_clean_serial`, `_matches` (read it for the type-alias table: ar, sg, ps,
repkit, grenade, rifle, ...), `_element_ok`, `_ownership_ok`, `search`, `cmd_catalog` (stats). The
database file is `config.serial_db_path`. Rows become `core.types.CatalogEntry`; the database's
`bulletType` 'electric' maps to vocab 'shock' at the edge (`vocab.normalize_element`). Element
verification calls `ops.describe(serial).element`; ownership calls `rules.serial_ownership`. The
legacy `search.last_skipped` side channel becomes `SearchResult.hidden_by_pack`.

## Invariants
- `labels_are_hints`: with `verify_element=True`, a row whose database element disagrees with the
  decoded serial is dropped and counted in `dropped_element_mismatch` (legacy found 3.3% of weapons).
- `filters_are_reported`: unowned rows are counted per pack in `hidden_by_pack`, never silently lost.
- `type_aliases_work`: `ar`, `assault_rifle`, `repkit`, `repair_kit`, `grenade`, `gadget`, `sg`, `ps` all return rows (legacy once returned none for ar/repkit).
- `deterministic`: same query twice -> identical result order.
- `dedupes_serials`.
- `matches_legacy`: for a battery of >= 40 queries (every type x several elements, class mods by
  character, name queries like 'anarchy', 'wombo combo'), the returned serials equal legacy `search`
  (same limit/flags), after mapping elements.
- `loads_9875`: count() == 9875.

## Health
count() > 0 and one known query returns a known serial. Implemented as checks `database_loads`, `known_query`
('anarchy' shotgun returns the known serial), `type_aliases` (ar, assault_rifle, repkit, repair_kit, grenade,
gadget, sg, ps all return rows), `find_by_serial`, `sample_rows_decode` (codec), `neighbours_verify`
(`ops.describe` and `rules.serial_ownership` answer correctly for the known serial). The first five depend
only on the database and codec; `neighbours_verify` fails while rules or ops are skeletons, which makes the
catalog DEGRADED (honestly: its searches would be unverified). Never raises; well under 1 s.

## Deviations from legacy
Parity bar met (`tests/modules/test_catalog.py`): a battery of 179 queries (every weapon type x every
element, class mods per character and per alias, name queries, rarity, manufacturer, every type alias,
limits 1/5/25/100/unbounded, `verify_element=False`, `include_unowned=True`, restricted owned-pack sets)
returns exactly the serials legacy `forge.search` returns, in the same order, with the same field values;
`dropped_element_mismatch` equals the rows legacy's own `_element_ok` rejects, `hidden_by_pack` totals
equal `search.last_skipped`, `stats()` equals `cmd_catalog`, and `find_by_serial` resolves all 8,520
distinct serials to their first row. The same battery is re-run against the real rules and ops modules
(`test_with_real_neighbours`). Differences, all deliberate:

**Shape**
- Rows are `core.types.CatalogEntry`. `bulletType` becomes a vocab element ('electric' -> 'shock', 'N/A'
  -> None; an unrecognised label -> None, counted in `diagnostics()`). `label` is legacy `enrich()`'s
  `manufacturerWeaponType or type`. A non-string `itemName` becomes '?'; other missing fields become ''.
- `search.last_skipped` (a function attribute: global, overwritten by the next call) is
  `SearchResult.hidden_by_pack`. Keys are pack IDS from `rules.serial_ownership` (`'bounty_pack_3'`),
  where legacy keyed by display label; use `rules.pack_label(id)` to print one. An unowned item for which
  rules names no pack is counted under `'unknown'`. Counted per distinct serial, over the rows scanned
  before `limit` was reached - exactly legacy's accounting, so a capped search reports only what it saw.
- `dropped_element_mismatch` is new. It counts ROWS rejected by the element check (legacy's check runs
  before de-duplication, so a mislabelled serial that repeats is counted per row), again only over the
  rows scanned before the cap.
- No module state. The database (path `config.serial_db_path`) is read lazily and cached per instance
  with its serial index and `stats()`; so are the neighbours' answers per serial (they are pure functions
  of the serial and the config). Legacy used a module-global `_DB`.
- Neighbours only through ports: element via `ops.describe(serial).element`, ownership via
  `rules.serial_ownership`, "can anyone read an element" via `data.available()` (legacy:
  `partsdb.available()`). `ItemInfo.manifest_ok == False` counts as "cannot tell".

**Query language**
- `SearchQuery.element` accepts every `vocab.ELEMENT_ALIASES` spelling (a superset of legacy's: adds
  'corrosion' and 'lightning'), any case, surrounding whitespace ignored. `character` goes through
  `vocab.normalize_character` ('dark siren' / 'Dark-Siren' / 'exo soldier'); a word that is not a
  character is still used as a raw keyword against `source`, as legacy did ('siren' works).
- `type` uses legacy's alias table verbatim (`TYPE_ALIASES` in `_match.py`, read-only). It stays a
  SUBSTRING match against `weaponType + ' ' + type`; so do `manufacturer`, `rarity` and the name query
  (kept on purpose: 'common' also matches 'Uncommon').
- All filter strings are stripped; legacy did not (`' ar '` found nothing). A blank string is no filter.
- An element name the vocabulary does not know ('plasma') matches nothing, like legacy (which compared the
  raw word to the database label; it only "worked" for the accident 'n/a', which is not preserved).
  It does not raise, so a typo in a loadout spec becomes an `unmatched` entry in the builder.
- `limit <= 0` is an empty result (legacy checked the cap after appending, so 0 or -3 returned ONE row).
  `limit=None` means no cap; a numeric string is accepted; garbage falls back to 25. A non-`SearchQuery`
  argument raises `TypeError` (a programming error, not a data problem).

**Failure handling**
- Database absent, unreadable, invalid JSON or not a list: `DataMissing` (message names the path) from
  `count/search/stats/find_by_serial`; constructing the module never reads the file, and a failure is not
  cached, so a file that appears later is picked up. `health()` and `diagnostics()` never raise.
- A row that is not an object, or has no '@U' serial (8 in the shipped file: 9,883 rows -> 9,875), is
  skipped at load and counted: `diagnostics()` -> `rows_in_file`, `rows_loaded`, `skipped_not_an_object`,
  `skipped_no_serial`, `unrecognised_element_label`.
- A neighbour that raises for a row (undecodable serial, sick module) NEVER crashes or shortens a search.
  As in legacy the row is ALLOWED through (the codec is at fault, not the player's entitlements), but the
  failure is counted per distinct serial in `diagnostics()` -> `element_check_errors` /
  `ownership_check_errors`, and `health()` fails `neighbours_verify` while the neighbours cannot answer.
  This is the one place a result can be less verified than it looks; `SearchResult` has no field for it,
  so `diagnostics()` is the way to see it.

**Additions**
- `stats()` returns the port's three tables (`by_type`, `by_weapon_type`, `by_rarity`) plus the ones legacy
  `catalog` printed: `by_manufacturer`, `by_element` (vocab names; 'N/A' = no element label) and
  `by_character` (class mods, from `source`). Each is ordered most-common-first, like `Counter.most_common()`,
  over database ROWS (so it sums to `count()`); the dicts are fresh copies. `by_rarity` is new.
- `diagnostics()` and `find_by_serial()` (first row wins; pasted quotes and a trailing comma are tolerated).

**Kept on purpose (legacy facts worth knowing)**
- 2,000 of the database's shield and grenade rows (1,477 + 523) carry an element label although the
  bitstream has no element for gear (legacy `references/catalog.md` says gear has none; that is true of the
  bitstream, not of the labels). Verification cannot judge them (`ops` reports None), so, like legacy, the
  label is trusted and they match element queries. Weapons are always checked. One weapon row has the label
  'N/A', so no element query can reach it.
- With the default owned set only 26 distinct serials (all `bounty_pack_3`) are unowned in this
  database; `hidden_by_pack` is empty for default-config searches. Tests use a config without that pack.

## Notes for callers (builder / cli)
- `forge.catalog.search(SearchQuery(...))` -> `SearchResult(entries, hidden_by_pack, dropped_element_mismatch)`.
  Defaults: limit 25, `verify_element=True`, `include_unowned=False`. Elements may be passed as the user
  typed them ('electric', 'ice'); entries always carry vocab elements ('shock').
- Entry fields are HINTS. `entry.element` is the database label (None = N/A); the element of the actual
  serial comes from `ops.describe`. Entries are frozen; `entry.serial` is the stored level-50 code.
- Report what was filtered: `hidden_by_pack` is `{pack_id: count}`; print `rules.pack_label(pack_id)` for a
  human label (the builder does not require rules, so label at the cli, or add the requirement). A positive
  `dropped_element_mismatch` is worth a one-line "N catalog labels disagreed with the serial".
- Misses are an EMPTY `entries`, never an exception (unknown element/character included). Only a missing
  or corrupt database raises (`DataMissing`).
- First search warms a per-instance memo (about 0.25 ms per candidate serial); later searches are cheap.
  The first `health()` (run by `Forge.build`) already loads the database (~0.1 s).
- `count()` is rows (9,875); `search` is serials (8,520 distinct).

