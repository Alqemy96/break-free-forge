# CONTRACT - module `save`

**Purpose:** open and re-wrap Borderlands 4 save files (PS5 and PC) and patch their YAML as text.
**Requires:** nothing (a leaf cell). Pairing saves with item names is the outer layer's job (cli/web call `ops.describe`).
**Class:** `SaveModule` in `src/bl4forge/modules/save/__init__.py` (`MODULE`). Port: `SavePort` in `core/ports.py`.
**Tests:** `tests/modules/test_save.py`, plus `save` cases in `tests/cli/test_cli_save.py` and `tests/web/test_web_save.py`.

## Formats
- PS5 (proven on a console, PS5 BL4 01.100.002): AES-256-ECB, FIXED key (no account XOR), PKCS7, zlib stream, then a 4-byte LE
  uncompressed length. NO adler32 footer. The game accepts our zlib level 9 (`78 da`) although it writes `78 9c`; it
  re-serialises the save on every load, so always edit the current save.
- PC (upstream `monokrome/bl4` `crypto.rs`, interop only): key = BASE_KEY with its first 8 bytes XORed with the Steam ID
  (digits only, u64 LE); footer = adler32 (u32 LE) + length (u32 LE).
- There is no integrity field inside the YAML.

## Keys
`config.toml` `[save] ps5_key`, `[save] pc_base_key` (64 hex digits each, git-ignored). Never in source or tests (tests use a
throwaway key). A missing key raises `SaveKeyMissing` naming the config key; `health()` stays OK (the engine works) and reports
"NOT configured" in its summary.

## Invariants (each has a test)
- decrypt -> encrypt -> decrypt gives identical YAML for all four real PS5 save fixtures the maintainer used (not shipped; tests that need them read BL4FORGE_SAVE_FIXTURES and skip without it) (compressed bytes may differ from the game's).
- Decrypt is strict: bad padding, corrupt zlib, wrong footer length or adler32 raise `SaveError`.
- Every edit changes exactly one existing line; only the value is replaced; line endings and `key: ` trailing spaces stay.
  Setting the old value back restores the text byte for byte. No YAML is ever parsed into objects and re-dumped
  (bl4.exe `set` rewrites ~226 lines).
- Refused (never guessed): unknown currency or slot, non-integer, out of range, a serial that is not `@U` + printable ASCII.
  No line is ever inserted.
- `write_copy` refuses the source path, hashes the source before and after, writes `<dest>.bl4forge.json`.
- Shared point pools (profile saves): `set_shared_point_pool` edits only `domains > local > progression_shared > point_pools > <name>`
  (0..2**31-1, existing integer line only; unknown name lists those present). The character save's top-level
  `progression: point_pools` is not reachable. `shared_pool_report` is read-only: value (TOTAL earned), sum of `points_spent`
  in graph `sdu_upgrades`, available = value - spent. CLI `save-set-point-pool`; web edit op `point_pool`; `save-open` shows it.
- Item refs: `backpack/slot_N`, `equipped/slot_N`, `lostloot/<index>`. Other `serial:` keys in the file are ignored.

## Not verified
- Level/XP: the XP-to-level table is unknown here; setting `level` without `points` may be re-derived by the game.
- Currency cap is the int64 max, not a game limit.
- In-game effect of raising the earned pool (echotokenprogresspoints): not verified. The int32 cap is an assumption (UNVERIFIED).
- Available = earned - sum(sdu_upgrades points_spent) is derived from one profile; the game may count differently.
