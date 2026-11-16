# CONTRACT - module `rules`

**Purpose:** Decide what the player may hold (content-pack ownership) and whether a serial is structurally sound.
**Requires:** codec, data
**Class:** `RulesModule` in `src/bl4forge/modules/rules/__init__.py` (export it as `MODULE`; split into more files inside this directory as you like)
**Read first:** `docs/AGENT_RULES.md` (module rules; see also docs/runbooks/DEVELOPER.md), `docs/ARCHITECTURE.md`, the `RulesPort` docstring in `core/ports.py`.
**Tests live in:** `tests/modules/test_rules*.py`

## Port to implement
`RulesPort` in `core/ports.py`.

## Port from legacy
`legacy/skills/bl4-loadout/scripts/partsdb.py`: `CONTENT_PACKS`, `pack_of`, `is_owned`, `owned_packs/set_owned_packs` (becomes
per-instance state seeded from `config.owned_packs`), `validate` (lines ~708-770), plus
`forge._ownership_ok` (lines ~171-187) which becomes `serial_ownership`. A serial's parts are resolved
the same way `describe` does it (bare `{N}` = own category index; `{cat:idx}` = other category):
reimplement that small walk here using `codec` and `data` rather than importing ops (ops depends on you).

## Invariants
- `ownership_is_per_part`: find a real item built with a DLC part under a base-game name (use the data) and prove it is caught.
- `story_pack_1_not_owned_by_default`, and `bounty_pack_5_is_harmless` (pre-listed).
- `owned_set_comes_from_config`: a Forge built with different `owned_packs` changes answers.
- `validate_structural_only`: pearlescents may carry two composition parts and are not flagged; a
  non-pearl with two is flagged; docstring never claims in-game validity.
- `matches_legacy`: `validate` and ownership agree with legacy for all 9,875 serials.

## Health
Known-answer: one base-game serial is owned; one Story-Pack-1 serial is not; pack_label('coregame') == 'Base game'.

## Deviations from legacy
Parity bar met (`tests/modules/test_rules.py`): `validate` returns the identical problem list for all
9,875 database rows (8,520 distinct serials; the only problem the data triggers is "no composition
part", 62 rows); `serial_ownership` returns the identical `(owned, missing_pack)` for every row under
the default owned set, and under four other owned sets (legacy re-run on every serial with a DLC part
plus a stride sample); `pack_of`, `is_owned` and `pack_label` match for every ref in `part_meta.json`.
Every validate problem kind (unknown part, two elements, level 0/256/100000, no level, firmware
pointer, no composition, non-pearl and pearl with two compositions) is also compared word for word on
synthetic serials. Everything below is a change of shape or a legacy behaviour deliberately NOT kept.

**Shape**
- No globals. Legacy `partsdb._owned_packs` / `set_owned_packs` are process-wide; the owned set is now
  per-instance, seeded from `config.owned_packs`. `owned_packs()` returns a `frozenset` (legacy: a copy of
  a `set`). `RulesModule.set_owned_packs(packs)` exists as an extra to the port and changes THIS instance
  only (a refused value raises `ConfigError` and changes nothing).
- `CONTENT_PACKS` (pack key -> label) is a read-only mapping in the rules package. `pack_label(key)` returns
  the key itself for a pack not listed there (legacy `CONTENT_PACKS.get(pack, pack)`), e.g. `bounty_pack_5`.
- The part walk is reimplemented against codec + data (`_walk.py`); nothing imports ops or legacy.

**Behaviour changes**
1. **`serial_ownership` names the first MISSING pack.** Legacy `describe` reported `content_pack`, the
   alphabetically first non-base pack among ALL packs seen (which can be an owned one), and
   `forge._ownership_ok` returned its display label. The port says "first_missing_pack", so it returns the
   pack KEY, alphabetically first among the packs that are not owned. Identical on the database (the only
   pack in use is `bounty_pack_3`); differs only on an item that mixes packs, where legacy could name a pack
   the player owns. Covered by `test_first_missing_pack_is_alphabetical`.
2. **Undecodable serials raise `SerialError`** from both `serial_ownership` and `validate` (legacy raised
   whatever the codec raised: ValueError/IndexError/..., and `forge._ownership_ok` swallowed it as
   `(True, None)` = allowed). The swallow-and-allow policy belongs to the caller (catalog does this); rules
   does not silently call garbage "owned".
3. **The base game is always owned**, even if `coregame` is missing from the owned set. Legacy was
   inconsistent: serial-level ownership ignored `coregame`, but `is_owned(cat, idx)` required it in the set.
   Both now agree. `owned_packs()` still returns exactly the configured set.
4. **List parts are judged per listed index.** A `{cat:[a b c]}` block means parts a, b, c of category
   `cat` (all 18,736 listed indexes in the database resolve that way). Legacy `describe` ignored the values and
   looked `cat` up as an index in the item's OWN table (usually missing, then labelled a "category link"),
   so a DLC part inside a list could never be caught. Ownership and validate now see each listed part.
   Identical on the database: no listed part is DLC-tagged, a composition or an element, and all resolve.
   Observable only with data the manifest does not have today (`test_list_parts_are_judged_per_listed_part`
   tags one listed part with a stub). ops' `describe` still walks list blocks the legacy way unless it chose
   otherwise; this module does not depend on that.
5. **"part index N does not exist in the X table" names the table the part was looked up in.** Legacy always
   printed the ITEM's category, even for a `{cat:idx}` part searched in another category. Identical for bare
   `{N}` parts.

**Kept on purpose (parity), for a central decision**
- The pearlescent exemption keys on the GOVERNING rarity (highest tier; first part wins a tie): an item whose
  governing component is `Vile` and which also carries a Pearl is flagged as a non-pearl with two. No data
  item has a Vile part today.
- A missing manifest does not raise: every part then reads as base game, `serial_ownership` is `(True, None)`
  (legacy), `validate` returns the legacy sentence "manifest data unavailable - cannot validate", and
  `health()` fails the `manifest` check. Callers that need to know check `data.available()`.
- The element part indexes (category 1, indexes 10-14) are a constant here, as in legacy (`vocab` has names
  only). The 62 database items with no composition part still produce the "no composition part" notice.
- `validate` only claims what the data supports. It never says an item is valid in game; the docstring says
  so and a test pins the wording.

## Notes for callers (ops / catalog / builder / cli)
- Reach it with `self.dep("rules")` and declare `"rules"` in `requires`. Instances hold no cache and no
  mutable state besides the owned set; calls are cheap (about 0.07 ms per `serial_ownership`, 0.15 ms per
  `validate` on a database serial).
- `pack_of(cat, idx)` and `is_owned(cat, idx)` are per part reference, `cat` the part's own category (for a
  bare `{N}` that is the item's category). They never raise; an unknown ref is `"coregame"` / owned.
- `serial_ownership(serial)` returns `(owned, missing_pack_key_or_None)`. `owned` is False when ANY part's pack
  is outside the owned set; the second value is a pack key (use `pack_label` for display), `None` when owned.
  It raises `SerialError` for a serial that does not decode: catch it where legacy allowed unreadable rows.
- `validate(serial)` is a list of strings, `[]` meaning "no structural problem found". It is not a
  validity claim; say "passed structural checks" in anything user facing.
- `RulesModule.set_owned_packs` is a convenience for one instance (e.g. a CLI flag); other modules should not
  call it, and the port is the contract.

