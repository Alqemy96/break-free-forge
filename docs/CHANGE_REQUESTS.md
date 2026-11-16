> Historical note (public copy): append-only design log from the build-out. Legacy/data references are to files not shipped here.

# Change requests (append-only)

Format: `- [module] wants <change> because <reason>; affects <modules>`

- [data] wants `DataPort.prettify_legendary` annotated `-> Optional[str]` because it returns None for a blank or numeric suffix (class-mod slot indexes such as `comp_05_legendary_04`), exactly like legacy; annotation only, behaviour unchanged; affects ops, catalog, render (callers must handle None).
- [data] wants a one-line text file `data/manifest/VERSION` (e.g. `2026-08-01`, the extract date the legacy README/plugin.json/SKILL.md state: "2026-08-01 extract, post-v1.9 / Bounty Pack 4") because the extract date is recorded nowhere inside `data/manifest/`, so `DataPort.manifest_version()` returns "unknown"; the data module already reads that file when present; affects the data/ owner (coordinator), cli/doctor output.
- [data] flags a legacy bug kept for parity: `is_weapon_category` matches the weapon word " ar" as a substring, so categories 145 "Def Sumofhisparts Arms", 236 "Shield Armor Pickup", 237 "Armor Shield" count as weapons (none is an item category in the 9,875-serial database); proposes whole-word matching, which would flip exactly those three ids; needs a central decision before data changes because ops derives the default "impact" element from it; affects ops, rules.
- [catalog] notes (no port change required, a decision for builder/cli) that `SearchResult.hidden_by_pack` is keyed by pack id (e.g. `bounty_pack_3`, as returned by `rules.serial_ownership`; legacy keyed by display label), and `builder.requires` is `(catalog, ops)` so the builder cannot turn an id into a label via `rules.pack_label`; either the cli does the labelling or `rules` is added to builder's requires; affects builder, cli.
- [builder] BLOCKED, wants a way to re-level a serial without leaving its declared neighbours. The builder must re-level every item (legacy `enrich` calls `codec.relevel`, and a failed re-level must become a warning on the item), but `BuilderModule.requires` is `(catalog, ops)` and neither neighbour exposes it: `CatalogPort` has no re-level, `OpsPort` has none either (only `CodecPort.relevel(serial, level)` does), and the builder may not call codec. Proposal A (preferred): add `OpsPort.relevel(self, serial: str, level: int) -> str` to `core/ports.py`, a thin delegate to `codec.relevel` in the ops module (ops already requires codec; it fits ops' purpose "modify ONE serial" and its "every transform returns a new serial string" invariant; raises `SerialError` when the level cannot be set). Proposal B: add `codec` to `BuilderModule.requires` (and to the graph in `core/ports.py`/ARCHITECTURE.md) so the builder calls `codec.relevel` and `codec.get_level` itself. Either works; A keeps the builder's surface smaller. The builder agent has stopped before writing code and will resume once the coordinator picks; affects ops (A: one method + test), builder (requires or its relevel call), core/ports.py, cli (none: it has every module).

## Resolutions (coordinator)
- [data] prettify_legendary annotation: ACCEPTED. `core/ports.py` now says `-> Optional[str]`; callers handle None.
- [data] VERSION file: ACCEPTED. `data/manifest/VERSION` added (2026-08-01, from the legacy plugin's own docs).
- [data] is_weapon_category " ar" substring: DEFERRED, parity kept. Categories 145, 236, 237 read as weapons but
  are not item categories in the database. Fix as one deliberate change after integration (whole-word match +
  a test over every category), not inside wave 2/3, so parity tests stay meaningful meanwhile.
- [catalog] hidden_by_pack keyed by pack id / builder cannot label: ACCEPTED as "cli labels". The cli has every module, so it
  turns pack ids into labels with `rules.pack_label`. `builder.requires` stays (catalog, ops). No port change.
- [ops, rules] list-part handling differs (`{cat:[a b c]}`): rules judges parts a,b,c of `cat`; ops follows legacy `describe`.
  Identical on the database today. Revisit with the is_weapon_category fix during integration (one deliberate change, one test).
- [ops] `set_element` does not check the item is a weapon (legacy behaviour kept): it would insert an element part into gear.
  Callers (cli, web) must only offer it for weapons. Candidate for a guard during integration.
- [builder] cannot re-level (relevel lives only in codec; builder.requires = catalog, ops): ACCEPTED, option A.
  `OpsPort.relevel(serial, level)` added to core/ports.py; ops delegates to `codec.relevel`; double updated; 2 tests.
  Builder's `requires` unchanged. (Phase-0 miss by the coordinator: the dependency graph omitted a re-level path.)
- [web-ui] wants `docs/WEB_API.md` to list fields the server already sends or accepts and the UI relies on: `/api/meta` `catalog_count`/`manifest_version` may be `null` (module down); `/api/search` adds `notes: [str]` and `decoded.owned` may be `null` (decode failed); reseed transforms add `seed`; 503 bodies carry `error.module`; `/api/build` requests also accept `label`, `name` (explicit entries: shown on the sheet instead of "Item") and legacy `label_name`; because the contract text omits them and `ui/src/api/types.ts` mirrors the server, not the doc; affects web (doc only, no code change).
