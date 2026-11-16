# CONTRACT - module `ops`

**Purpose:** Understand and modify one serial: identify, element, seed, part swap, diff.
**Requires:** codec, data, rules
**Class:** `OpsModule` in `src/bl4forge/modules/ops/__init__.py` (export it as `MODULE`; split into more files inside this directory as you like)
**Read first:** `docs/AGENT_RULES.md` (module rules; see also docs/runbooks/DEVELOPER.md), `docs/ARCHITECTURE.md`, the `OpsPort` docstring in `core/ports.py`.
**Tests live in:** `tests/modules/test_ops*.py`

## Port to implement
`OpsPort` in `core/ports.py`.

## Port from legacy
`legacy/skills/bl4-loadout/scripts/partsdb.py`: `describe` (358-480), `rarity_estimate`, `format_odds`, `RARITY_WEIGHTS`,
`set_element`, `get_seed/set_seed`, `part_list`, `swap_parts`, `diff`, `PartRef`.
Differences by design: `describe` returns `core.types.ItemInfo`; `element` is a vocab name
(lower-case, `impact` for an element-less weapon, None for gear) where legacy returned 'Cryo'/'Impact';
rarity ranks come from `core.vocab.RARITY_RANK`; ownership/pack come from `rules`
(`pack_of`, `is_owned`, `pack_label`), not module globals; the seed uses `codec.int_at/with_int_at`.
`swap_parts` signature keeps `allow_cross`.

## Invariants
- `bitstream_is_authoritative`: describe never reads a database label.
- `pearl_rarity_from_meta`: a `comp_05_legendary_*` part tagged Pearl in part_meta describes as Pearl; test with real serials.
- `highest_tier_governs_and_others_reported`: items with several components expose `other_components`.
- `set_element_round_trips`: setting an item to its own element returns the identical serial; `impact` strips the part.
- `swap_refuses_cross_category` unless `allow_cross=True`.
- `gear_has_no_element`: shields/class mods/repkits/enhancements report element None.
- `describe_never_raises_without_manifest`: with empty data dir, manifest_ok False plus a warning.
- `matches_legacy`: for all 9,875 serials: category_id, level, rarity, legendary_name, display_name,
  part labels, owned, content_pack equal legacy (element compared after `normalize_element`).
- `odds_are_base_rates`: format_odds text never presents luck-modified numbers as exact; bosses with no rate list the source without a percentage.

## Health
describe() on 2-3 embedded known serials (weapon, shield, pearl) returns expected category/rarity.

## Deviations from legacy
Parity bar met (`tests/modules/test_ops.py`): over all 9,875 database rows `describe` equals legacy on
category_id, category, level, rarity, element (after `vocab.normalize_element`), legendary_name,
display_name, every part (token_index, category, index, raw, name, category_link, label), other_components,
tokens, content_pack(+label), owned and warnings; `rarity_estimate`/`format_odds` are identical;
`set_element` is identical for every weapon x every element (2,449 distinct weapons x 6); `get_seed`
is identical for every row and `set_seed` for 500 sampled serials x 5 seeds; `swap_parts` (400 same-category
pairs, 80 cross-category pairs with `allow_cross=True`, the error cases) and `diff` (440 pairs) are identical.
The database holds NO pearlescent and NO item needing unowned content, so those cases are built from real
parts: for each part_meta entry that is a Pearl or carries a content pack, a database serial of that category
gets the part REPLACED into its composition slot (or APPENDED), and `describe` on those 137 serials is
compared to legacy as well (this is where Pearl-from-meta, `other_components` and `owned=False` are proven).

**Shape (by design)**
- `describe` returns `core.types.ItemInfo` (frozen, tuples) instead of a dict. `manifest` is `manifest_ok`;
  `other_components` is always present, a tuple of `(rarity, name)` (legacy: absent, or a list of dicts);
  `owned`, `content_pack`, `content_pack_label` are always set (legacy omitted them without a manifest; the
  defaults are `True`, `coregame`, `Base game`). `ItemInfo.serial` is the argument exactly as given.
- `element` is a vocab name: `cryo fire radiation shock corrosive impact`, `impact` for an element-less weapon,
  `None` for gear. Legacy returned `Cryo`/`Impact`. `diff` rows carry the same vocab names.
- `PartRef` is the frozen `core.types.PartRef`; legacy's `.part` (raw codec Part) and `to_dict` are gone.
  `PartRef.token_index` indexes the codec's `Blocks`; `swap_parts` positions index the PART blocks only.
- Rarity ranks come from `core.vocab.RARITY_RANK` (identical numbers), the tier word of a `comp_0N_` name from
  `vocab.RARITIES`. Element part indexes (`{1:10..14}`), `SEED_POSITION = 5` and the world-drop weights live here
  (`_odds.RARITY_WEIGHTS`, total 106.1853) and are immutable constants.
- Ownership/packs come from `rules` (`pack_of`, `is_owned`, `pack_label`), per part; there is no module-level
  owned-pack set (legacy `set_owned_packs` was a process global). Rarity, display name and pack tags come only
  from `data.part_meta`; nothing is parsed out of a part name except the tier-word FALLBACK legacy had when
  part_meta has no entry (`comp_0N_` -> `RARITIES[N-1]`).
- No state of any kind: no caches, no globals; every method reads its neighbours afresh.
- `rarity_estimate` takes the `ItemInfo` (legacy took the describe dict and callers re-described) and returns a
  plain, mutable dict; `dedicated_tier_rates` is a deep copy (legacy leaked the live drops.json cache object).
- `swap_parts` parameters are `base`, `source` (legacy `base_serial`, `source_serial`); the copied `Part` is
  shared, not cloned (it is frozen).

**Errors**
- Everything raises `SerialError` (legacy: `ValueError` for an unknown element, a refused cross-category swap,
  an out-of-range position, a missing seed field or part list; codec exceptions for bad serials).
- `swap_parts` also refuses non-integer positions (`True`, `"1"`, a bare string), which legacy ignored or crashed on.

**Value ranges (legacy silently corrupted)**
- `set_seed`: legacy masked with `0xFFFFFFFF`, and the codec could not store more than 65535, so
  `set_seed(s, 70000)` stored a different number without a word. Now seeds 0..2**31-1 are stored exactly (codec
  VARBIT above 65535) and anything else (negative, bool, float, str, None) is `SerialError`. Real seeds are <= 4095,
  where results are byte-identical to legacy.
- `set_element`: element words come from `vocab.normalize_element` (a superset of legacy's aliases, e.g.
  `non-elemental`); `physical` and the empty string, which vocab does not know, are still accepted locally as
  "strip the element", exactly as legacy did.

**Unchanged on purpose (legacy behaviour kept; flagged so nobody "fixes" it by accident)**
- `data.is_weapon_category` quirk: ops derives the default `impact` element from it, so categories 145, 236 and
  237 (not item categories in the database) would read as weapons. Deferred centrally (CHANGE_REQUESTS
  Resolutions); ops needs no change when data's matching is fixed.
- `set_element` does NOT check the item is a weapon: asked to, it inserts a `{1:N}` part into a shield just as
  legacy did, and `impact` on gear is a no-op. Callers (builder) decide whether that makes sense.
- Weapon with several element parts (invalid, none in the database): `describe` reports the LAST, `set_element`
  replaces/removes the FIRST; `rules.validate` is what flags it.
- An element or composition part is recognised only if its index resolves to a raw name in the manifest.
- `rarity` is `None` (not an error) for the 62 database items with no composition part; `display_name` then
  falls back to the category name. A composition with a numeric suffix (class-mod slots) has no name.
- `swap_parts` is structural only: same category (or `allow_cross=True`) and in-range positions. It never
  claims the result is valid in game.
- `format_odds` is built from base rates: `~1 in N`, bosses without a rate listed with no percentage, and no
  odds at all for Pearl/Vile (no world-drop weight exists for them).

## Notes for callers (catalog / builder / cli)
- `ops = self.dep("ops")`; declare `requires = (..., "ops")`. Stateless and thread-safe; `describe` is ~0.2 ms.
- `describe(serial)` is the one call to trust a serial: it raises `SerialError` only if the string cannot be
  decoded. Check `info.manifest_ok`, `info.warnings` and `info.owned`; never read rarity/element from a catalog
  label when a decoded value exists. `info.element` is a vocab name (`None` for gear), compare directly to
  `vocab.normalize_element(user_input)`; an element-less weapon is `impact`, not `None`.
- Odds: `ops.format_odds(ops.rarity_estimate(info))` (empty string when there is nothing to say).
- `set_element(serial, "impact")` strips; `set_element(serial, e)` for an item that already has `e` returns the
  same string. Do not call it on gear.
- `swap_parts(base, source, positions)`: positions are indexes into `part_list(...)` (PART blocks), not
  `token_index`. Cross-category needs `allow_cross=True`.
- `set_seed` takes 0..2**31-1; `get_seed` is `None` for a serial without the field.
- Every transform returns a NEW serial string. A level that cannot be set is the codec's `relevel` problem, not ops'.
