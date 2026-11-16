# Researcher runbook: findings, method, open problems

Subject: **Borderlands 4, PS5, version 01.100.002**. Labels: **proven** = tried in the real game by the
maintainer; **recorded** = a result the maintainer's notes state that this tree does not re-derive in code
(treat as a claim); **UNVERIFIED** = not tested.

This document deliberately leaves out the save key, where it was found, and any console details. The method that
finds a key is described; the key and its location are not, and a fixed key is something the publisher can
rotate. Obtain your own, for your own saves.

## 1. PS5 save format (proven)

A PS5 character or profile save, `gbxsavegame.sav`, once the console's own outer layer is removed by whatever
transfer tool you use, is:

```
AES-256-ECB( PKCS7( zlib_stream || uint32_LE(uncompressed_length) ) )
```

- **Cipher/key:** AES-256 in ECB mode with a **fixed 32-byte key**. No account id, Steam id or other per-user
  value is mixed in; the same key decrypts every save of this game version. (PC differs: its key is a base key
  with the first 8 bytes XORed with the account id as a little-endian u64.)
- **Padding:** PKCS7 to 16 bytes, **except** that when `zlib + 4-byte trailer` is already a multiple of 16 the
  game writes **no** padding. Decrypt must try the padded reading first and fall back to the unpadded one
  (`modules/save/_container.py` does; both are validated by the zlib stream and trailer).
- **Trailer:** 4-byte little-endian uncompressed length. **No adler32** (PC appends adler32 and then the length).
- **Plaintext:** UTF-8 YAML, roughly 26 KB / 830 lines for a mid-game character, with top-level keys such as
  `state, onlinecharacterprefs, pips, globals, stats, activities, missions, save_game_header, progression,
  timed_facts` plus discovery blocks.
- **No integrity field exists inside the YAML** (`save_game_header` holds only a guid, a timestamp, the original
  platform and a changelist). A one-line content edit has nothing to invalidate, and edits load.
- **The compressor does not matter.** The game accepts zlib level 9 (`78 da`) even though it writes `78 9c`
  itself. Re-encrypting unmodified text produced a loadable save with identical values.
- **The game re-serializes the save on every load** (same values, new bytes). After any in-game load, rebuild
  your edit from the current save; never reuse an edit made before that load.
- **Edit as text, not as objects.** Do not parse and re-dump the YAML: a whole-document re-serializer
  rewrites hundreds of lines (turns empty values into nulls, lowercases booleans, strips trailing spaces).
  `modules/save/_yamltext.py` changes exactly one existing line per edit and never inserts lines.
- Four images exist per title (character, profile, and the platform's own backup of each); one key decrypts all.

### Method that finds a fixed game-layer key (described, not applied here)

When a game compiles a fixed key into its binary, you do not need to trace the save routine:

1. Take a **memory dump of the running game** (or its data and code segments) that you obtained yourself, and one
   encrypted save of the same build.
2. **Brute scan with stride 1:** treat every byte offset of the dump as a candidate 32-byte (and 16-byte) key.
   About two billion candidates for a 100-200 MB dump, a few minutes on a many-core machine in a compiled
   language using the standard library's AES.
3. **Oracle:** a candidate is correct only if AES-ECB decrypt followed by padding removal gives a *complete zlib
   stream that fully decompresses with no error*, with the trailer length equal to the decompressed size. The
   false-positive rate is negligible, so no code tracing or key-schedule heuristics are needed.
4. The first run produced exactly one hit; only the raw key was present, not an expanded key schedule.

A game update can change the key; rerun the scan on the new build. Whether the same pattern holds for other
titles is UNVERIFIED (each would need its own scan).

### What edits worked in game (proven)

| Edit | Result |
|---|---|
| Re-encrypt unchanged text | loads, values identical |
| Cash / eridium value | loads; shows the new value |
| Character level to **70** | works; level 70 is the cap |
| Item serials | replaced serials load; an item at **level 70 is accepted after re-leveling a known serial** |
| Profile **unlockables** (cosmetics) | unlocked; see 2 |

## 2. Progression and unlock details

- **XP curve (recorded):** points needed for level L follow about `60 * L^2.8`, capped at level 70. This tree does
  not encode the curve (`save-set-level` warns when you set a level without XP). Whether the game re-derives level
  from XP after a level-only edit is UNVERIFIED. Safest is to set level and a matching XP value together.
- **Profile unlockables vs `pips_list` "new" markers (recorded):** the profile save has the real unlock list
  (what you own) and a separate list of "new" badges (`pips_list`). Unlocking cosmetics means editing the unlock
  list; touching only the "new" markers only changes the badge. No shipped command does this; it was a text edit
  of the profile YAML.
- **Shared point pools** (profile): `save-set-point-pool` edits an existing integer under
  `domains > local > progression_shared > point_pools`. The value is the TOTAL earned, not the available amount;
  available = earned - spent (spent summed from the upgrade graph). The in-game effect of raising the pool is
  UNVERIFIED, as is the int32 cap.
- **Item level 70:** relevel a serial you know is good (`relevel` in the codec); do not hand-build one.

## 3. Loot tables (PS5 paks): method and findings

Loot behavior lives in the game's data tables (Nexus config store, `.ncs`, packed in paks). The builder
(`lootpak` cell) retargets values of **existing** leaves only.

### Method

- **Leaf locating without hard-coded offsets.** A leaf list in binary order (bit position, width, pool index,
  string) is obtained from `ncstool`; a decode (`bl4 ncs show`) gives the same leaves with field names in
  alphabetical order. A table is anchored by its table-name leaf, row-struct leaf and first row name; each row's
  leaves are the next N leaves, N taken from the decode. Then a **sentinel probe**: the window's leaves are set to
  distinct sentinel pool strings in a scratch copy and decoded; the decode lines that change say which field each
  leaf is. The binary order inside a struct is therefore learned, never assumed.
- **Binary order of `table_enemydrops` per-rank probabilities:** `classmods, enhancements, repkits,
  grenadesorgadgets, shields, guns` (not the alphabetical order the decode prints).
- **Decode-diff gate:** the built pak is extracted and decoded again; its diff against the base must be exactly
  the planned lines or the build is rejected.
- The string pool is not grown: a value must already be in the pool (numbers are spelled `%.6f`).

### Findings

- The baseline cause of "very little gear" was `table_enemydrops`: by rank, the per-rank gun probability
  was low (a few percent for the weakest ranks, about a tenth for the strongest). Earlier theories about weights
  and inserts were retracted.
- **`Rarity_Balance`** `base_weight` per tier shifts the colour mix; lowering the common tiers increased blue and
  purple share (observed, not counted).
- **Inserting a struct into `Normal` stopped Normal drops** (the `rarity_modifier` insert). The v1 builder
  therefore forbids inserts: edit existing leaves only, and refuse a row that lacks a field.
- A "greens fix" and the dedicated-drop tables changed the colour mix; "difficulty lootluck" on the Normal row
  made a visible difference at a low value and a worse feel at a very high one (impressions, not counts).
- A second table file in the same pak loads without harm, but an inventory-size edit in it had no effect
  (cause not found).
- **Mixed, unexplained:** a build raising weak-rank gun odds to 0.60/0.35 (strong rank 0.90/0.45) passed in game;
  a later build raising them further to 0.75/0.45 produced **zero gear in 20+ kills**; restoring the earlier
  build was done by renaming and was not re-counted afterwards. A following build that was the earlier good one
  plus a spawn-table change (no loot change) also showed almost no guns. So "the larger values broke drops" is
  **not established**; drop variance or an install-related effect is open.
- **Solo spawn table** (`oneplayer.constant` set to each row's 3-player value, default +2): **no visible
  effect.** Either solo spawners do not read this table, or the definitions lack a player-count modifier.
- **A loot-luck code patch** (a runtime patch of the luck resolver, not a data edit): **no visible effect** at
  x2; x10 crashed after a kill. That tooling is not included.
- Luck on the difficulty row feeds a luck category summed with base and gear luck. No decoded field ties luck to
  drop **quantity**; whether luck changes the amount of loot was never counted.

## 4. Open questions

1. **Why did the two later builds (the 0.75/0.45 build and the build after it) lose gear drops?** Needs a
   controlled count: several hundred kills per build, same area, same difficulty, with the vanilla pak as control,
   and a record of exactly which file is mounted.
2. **Which flag gates the higher difficulty mode (UVHM)?** The table `difficulty_uvh` is whitelisted in the
   builder with no golden test; the save-side flag that unlocks the mode is unknown.
3. **Item stat ranking.** The serial carries parts and a variance seed, but which parts and rolls are "better" is
   not modeled; `reseed` rerolls variance without any ranking.
4. Do solo spawns read any table the builder can reach? Is a player-count modifier absent in the spawner defs?
5. Does the game keep an item it did not generate, over many save/load cycles? (Single items persisted; no
   long-run test.)
6. Does the same fixed-key-in-binary pattern hold for other platforms or titles?
7. The real accepted ranges for currency and level (tooling caps at int64 and level 100; the game's own caps are
   unmeasured).

## 5. Rules of method worth keeping

- Trust the decoded serial, never a database label (labels were wrong on roughly 3% of weapons).
- Rarity comes from explicit part metadata, never from a part name.
- One change per test; take a fresh backup before each write; the game re-writes saves on load.
- "Passed structural checks" is never "valid in game".
- State what was counted and what was only an impression.
