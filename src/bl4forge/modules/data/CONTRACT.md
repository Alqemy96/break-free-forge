# CONTRACT - module `data`

**Purpose:** Serve the game's manifest tables (categories, parts, rarity/pack meta, drops) as read-only lookups.
**Requires:** nothing (a leaf cell)
**Class:** `DataModule` in `src/bl4forge/modules/data/__init__.py` (export it as `MODULE`; split into more files inside this directory as you like)
**Read first:** `docs/AGENT_RULES.md` (module rules; see also docs/runbooks/DEVELOPER.md), `docs/ARCHITECTURE.md`, the `DataPort` docstring in `core/ports.py`.
**Tests live in:** `tests/modules/test_data*.py`

## Port to implement
`DataPort` in `core/ports.py`.

## Port from legacy
The data-loading half of `legacy/skills/bl4-loadout/scripts/partsdb.py`: `MANIFEST_DIR`, `available/_require`, `_read_tsv`,
`category_names`, `_category_files`, `part_table`, `item_names`, `drops`, `drops_by_item`,
`part_meta/meta_for`, `prettify_part`, `prettify_legendary`, `is_weapon_category`.
Manifest location is `config.manifest_dir` (never computed from `__file__`). Do NOT port ownership,
describe, validate, swap, odds: those belong to rules and ops.
`ManifestMissing` becomes `DataMissing` (raised only by `require()`).
`manifest_version()`: find where the extract date lives in the manifest (search `part_meta.json`,
`index`-like files, README of the seed); return 'unknown' if nowhere. Report what you found.

## Invariants
- `lookups_never_raise_when_missing`: point config at an empty dir; every lookup returns empty, `available()` is False.
- `rarity_and_pack_from_part_meta`: `part_meta(...)` exposes the explicit fields; a test proves a
  `comp_05_legendary_*` part tagged Pearl is reported as Pearl (find a real example in the data).
- `per_instance_cache`: two DataModule instances with different data dirs return different data.
- `matches_legacy`: for every category, `part_table` equals legacy; `category_names`, `item_names`,
  `drops`, and `part_meta` for every ref equal legacy.

## Health
`available()`, category names non-empty, part-table count matches the files on disk (161 expected;
report the real number), part_meta non-empty.

## Calling notes (for rules / ops / catalog)
- `self.dep("data")` gives the module. Every lookup is safe to call without data: check `available()`
  when you need to report `manifest_ok=False`; call `require()` only if you want to fail loudly.
- Results are shared, read-only `dict`/`list` subclasses (`==`, `isinstance(..., dict)`, `json.dumps`
  all work; any mutation raises `TypeError`). Take `dict(x)` / `list(x)` / `copy.deepcopy(x)` for a mutable copy.
- `part_meta(cat, idx)` returns the game's entry verbatim: any of `name`, `rarity`, `pack`, `tags`
  (a missing key means the game did not tag it). It does NOT default `pack` to `coregame` (rules does that)
  and never infers rarity from the part name. `{}` when the ref has no entry.
- `prettify_part` / `prettify_legendary` are display labels. The tier word in `prettify_part("comp_05_legendary_x")`
  is the name token, so a Pearl reads "Legendary - X"; take rarity and display name from `part_meta`.
  `prettify_legendary` returns `None` (not a string) for a blank or numeric suffix, like legacy.
- `item_names()` keys are lower-cased (`np_hellwalker`); `drops_by_item()` keys are lower-cased item names.
- `part_table(unknown_id)` is `{}`; ids are ints; `part_table(None)` is `{}`.
- `manifest_version()` is `"unknown"` for the shipped data (see Deviations, "manifest_version").

## Deviations from legacy
Everything here is exercised in `tests/modules/test_data.py` / `test_data_edges.py`. Parity over every
category, part ref, part name, item name and the 9,875-serial database holds except where listed.

Intentional changes
1. **Missing data never raises from lookups.** Legacy `_require()` raised `ManifestMissing` from
   `category_names/part_table/item_names/drops/drops_by_item`, and an unreadable or corrupt file raised
   OSError/ValueError. Now: `available()` False => every lookup returns an empty read-only mapping (`False` for
   `is_weapon_category`); a missing/corrupt file inside a present manifest => that lookup is empty and
   `health()` reports the file. Only `require()` raises, and it raises `DataMissing`. Legacy `part_meta()` kept
   serving `part_meta.json` even without `parts/`; now it too is empty when `available()` is False.
2. **No globals; location from config.** Legacy cached in module-level variables and located the manifest from
   `__file__`. Now: per-instance caches (thread-safe lazy load), directory is `config.manifest_dir`.
   While the manifest is absent nothing is cached, so data that appears later is picked up.
3. **Read-only results** (`FrozenDict` / `FrozenList`, nested). Legacy handed out its live cache dicts.
   Equal to the legacy values; mutation raises `TypeError`; copy/deepcopy/pickle yield plain mutable values.
4. **API shape follows the port.** Legacy `part_meta()` (whole table) and `meta_for(cat, idx)` become
   `part_meta(category_id, index)`; `pack_of/is_owned/owned_packs` belong to rules and are not here. The whole
   table is still reachable per ref; there is no public "all entries" method.
5. **Part-file discovery is deterministic**: `parts/*.tsv` are scanned in sorted order, so if two files ever
   claimed the same category id the later name wins every time (legacy: `os.listdir` order). The shipped data has
   none (161 files, 161 distinct ids); `health()` fails `part_tables` if it ever happens, or if a `.tsv` does
   not match `<slug>-<id>.tsv`.
6. **Unknown categories are not negative-cached** (legacy stored `{}` per unknown id, unbounded growth).
7. **Never-raise hardening on odd input** (legacy would raise): a TSV id cell like a superscript digit is
   skipped; `prettify_part(None)` is `""`; an unhashable category id gives `{}` / `False`.
8. **`manifest_version()`** is new. Finding: the extract date lives nowhere inside `data/manifest/`. Searched
   `part_meta.json` (only `"cat:idx"` keys), `drops.json` (`"version": 1` is the file's schema version, not a
   date), `gear_types/manufacturers/weapon_types.json`, the TSV headers: nothing. The date appears only in the
   legacy docs (`legacy/README.md`, `.claude-plugin/plugin.json`, `SKILL.md`: "2026-08-01 extract, post-v1.9 /
   Bounty Pack 4"), which this module must not read at runtime. So it returns `"unknown"` unless the manifest dir
   contains an optional text file `VERSION` (first non-blank, non-`#` line is returned, e.g. `2026-08-01`).
   Change request filed to add that file.

Legacy behaviour preserved ON PURPOSE (parity), flagged for a central decision
- **`is_weapon_category` substring quirk.** The weapon word `" ar"` is matched as a substring, so
  `"Armor Shield"` (237), `"Shield Armor Pickup"` (236) and `"Def Sumofhisparts Arms"` (145) read as weapons.
  None of them is an item category in the 9,875-serial database (shields there are 279, 283, ...), so no
  parity result is affected today; it would give an Impact element to a gear item whose category id was one of
  those three. A whole-word match would fix it and flip exactly those three ids. Held (see CHANGE_REQUESTS).
- **`prettify_part` rarity prefix comes from the name token** (tier number in `comp_0N_...`), so Pearls named
  `comp_05_legendary_*` print "Legendary - X" (14 of the 20 pearlescents). Display only; nothing here uses it
  as rarity. Callers must use `part_meta` for rarity and display name (as legacy `describe` does).
- **`prettify_legendary` returns `None`** for a blank/numeric suffix although the port annotates `-> str`
  (annotation fix requested).
- `item_names` keys lower-cased and values stripped; `part_meta` has no `pack` default; `available()` means the
  `parts/` directory exists.
