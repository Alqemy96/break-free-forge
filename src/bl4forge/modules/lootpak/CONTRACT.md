# CONTRACT - module `lootpak`

**Purpose:** build a PS5 loot pak (`pakchunk100-ps5_P.pak`) from one TOML config, replacing hand-run `REGEN.txt` recipes.
**Requires:** nothing (a leaf cell; never touches `save`).
**Class:** `LootPakModule` in `src/bl4forge/modules/lootpak/__init__.py` (`MODULE`). Port: `LootPakPort` in `core/ports.py`
(`load_config(path)`, `plan(config)`, `build(config, out_dir)`; progress lines go to the settable attribute `cell.log`).
**Tests:** `tests/modules/test_lootpak.py` + `tests/lootpak_helpers.py` (the fake tool set).
**CLI:** `lootpak-plan CONFIG` (prints the plan, writes nothing), `lootpak-build CONFIG OUTDIR`.

## v1 scope
- ONE operation: `set_leaf` = retarget the value of an EXISTING leaf (`ncstool set-bits`) to a string ALREADY in the pool.
- NO struct or leaf inserts (in game, inserting `rarity_modifier` into Normal stopped Normal drops). A row that lacks a field is
  an error. NO `add-strings`: a value not in the pool is an error (`0.33` -> "not in the string pool"); prefer an existing pool
  string (numbers are spelled `%.6f`, e.g. `0.600000`; more precision is refused).
- Editable (whitelist in `_config.SECTIONS`, with ranges): `[enemydrops.<Rank>]` the six `*_probability`, `exp_multiplier`,
  `rarity_modifier.*modifier`; `[rarity_balance.<Tier>]` `base_weight`; `[difficulty_standard|difficulty_uvh.<Row>]` `lootluck`;
  `[lootablebalance.<Row>]` the six modifiers the row already has; `[spawnbalance.<Row>]` ONLY `oneplayer_constant`
  (= `oneplayer.constant` of `Table_PlayerCountSpawnBalanceData`, 0..20; solo play; the other columns/fields are refused).
  Row names with `+`/`&` are quoted in TOML. Rows are matched case-insensitively against the base decode.
- Config: `[meta] name notes`, `[base] raw inventory reference_pak (+ optional *_sha256)`, `[pak] name mount seed`
  (defaults = the recipes: `pakchunk100-ps5_P.pak`, `../../../`, `2190688979`). Relative `[base]` paths resolve against
  `[lootpak] modwork` in `config.toml`. Examples: `examples/lootpak/out13.toml`, `out14.toml`, `out16.toml`.

## Tools (config.toml, git-ignored; it names programs that get RUN, see DISCLOSURE.md)
`[lootpak] ncstool, bl4, uextract, modwork` (+ optional `protected_dirs = "a;b"`). Only `_tools.py` runs a program (subprocess,
no shell); tests replace it with `FakeTools`. No console or network code. Installing a pak is a separate human step.

## How leaves are found (never by constant)
1. `NCS_LEAFLOG=1 ncstool leaves <raw>` gives every leaf in BINARY order (BINOFF, bit position, width, pool index, string).
2. `bl4 ncs show` gives the same leaves with field names in alphabetical order.
3. A table is anchored by its table-name leaf + row-struct leaf + first row name (up to two `true`/`false` leaves, i.e.
   `always_loaded_struct`, may sit between the struct leaf and the first row name; anything else refuses); each row's leaves are the next N leaves,
   N = the row's leaf count in the decode (checked: every row-name leaf must be where expected).
4. The window's leaves are set to distinct sentinel pool strings in a scratch copy, which is decoded; the decode lines that
   change say which field each leaf is. So the binary order inside a struct (in `table_enemydrops` the six probabilities are
   classmods, enhancements, repkits, grenadesorgadgets, shields, guns) is learned, never assumed.
5. Cross-check: the leaf's own string must equal the decoded value of its field, else the edit is refused.

## Invariants (each has a test)
- The plan is printed before anything is written; planning writes only scratch. The base files are hashed before and after.
- Pipeline: hash inputs -> plan -> set-bits -> wrap -> copy inventory -> mkpak (reference pak's version, mount, seed) -> uextract +
  decode -> decode-diff gate -> `manifest.json` (sha256 in/out, sizes, plan, diff, tool sha256) + generated `REGEN.txt`.
- **Gate:** the decode diff vs the base decode must be EXACTLY the planned lines (same line, same old and new text). An extra,
  missing or wrong change fails the build: the pak is renamed `.REJECTED`, `FAILED.txt` is written, no manifest. The inventory
  and table inside the pak must also equal what was given to mkpak.
- **Write protection:** refused are the base's folder (or inside it, or a folder around it), any existing `outN` folder or
  non-empty folder, anything under a folder named `backups`, and `protected_dirs`. Every write goes through `ensure_inside`.
- Golden: `out16.toml` (spawnbalance, base out14's raw) gives `82adbfed...5107` (290324 bytes; a build into scratch, not installed or
  tested in game). `out13.toml` from the out10 raw table gives sha256 `0c9142ba...cda4`; `out14.toml` from the out13 raw table gives `23364fa4...5d`
  (both 290324 bytes). Skipped when the tools or modwork files are absent.

## Not verified / not done
- No in-game result is claimed; the pak is only proven to differ from its base by the planned decoded lines.
- "Rebuild the base from its own inputs and require byte identity" (design step 6) is not implemented in v1; an empty plan copies
  the base raw and re-wraps it.
- `lootablebalance` and `difficulty_uvh` sections are whitelisted but have no golden test; a row whose binary window does not
  match its decode is refused rather than guessed.
- The real pool holds two strings twice (`0.003000`, `0.140000`). A leaf already holding either copy counts as unchanged; a
  retarget to such a value uses the lowest index and says so in the plan notes.
