# CONTRACT - module `codec`

**Purpose:** Turn '@U...' serials into bitstream blocks and back, bit-exactly.
**Requires:** nothing (a leaf cell)
**Class:** `CodecModule` in `src/bl4forge/modules/codec/__init__.py` (export it as `MODULE`; split into more files inside this directory as you like)
**Read first:** `docs/AGENT_RULES.md` (module rules; see also docs/runbooks/DEVELOPER.md), `docs/ARCHITECTURE.md`, the `CodecPort` docstring in `core/ports.py`.
**Tests live in:** `tests/modules/test_codec*.py`

## Port to implement
`CodecPort` in `core/ports.py`.

## Port from legacy
`legacy/skills/bl4-loadout/scripts/bl4codec.py` (690 lines; itself a port of Nicnl/borderlands4-serials, AGPL-3.0 - see LICENSING.md and NOTICE).
Keep the algorithm bit-exact. Change the *shape*: use `core.types.Block/Part` (frozen), return
`Blocks` tuples, raise `SerialError`, and drop the legacy classes. `int_at` / `with_int_at` come from
the legacy `_int_at_pos` helper and how `partsdb.get_seed/set_seed` use it (`SEED_INT_POS = 5`).
Level handling is legacy `_level_block`, `get_level`, `relevel`. `get_category_id` is legacy
`get_manufacturer_index`.

## Invariants (each gets a test named after it)
- `roundtrip_is_byte_identical`: encode(decode(s)) == s for all 9,875 database serials.
- `decode_matches_legacy`: parts_string(decode(s)) equals legacy for every serial.
- `relevel_matches_legacy`: relevel(s, 60) equals legacy for every serial; get_level reads 60 back.
- `pure`: no file access, no globals, inputs unchanged (Blocks are immutable; assert it).
- `errors_are_serialerror`: garbage input ('', '@U', random text, truncated serial) raises SerialError only.

## Health (known-answer)
Embed 3+ real serials as constants with their expected level and category id; `health()` decodes,
round-trips and re-levels them. No file access from the module.

## Deviations from legacy
Parity bar met: over all 9,875 database rows (8,520 distinct serials) decode -> `parts_string`, block
structure, `encode(decode(s))`, `relevel(s, 60)`, `get_level`, `get_category_id`, `int_at(.., 5)` and
`with_int_at(.., 5, v)` + `encode` are identical to legacy (`tests/modules/test_codec.py`). Everything
below is either a change of shape or a legacy bug that is deliberately NOT preserved. None of them can
trigger on a well-formed serial from the database.

**Shape**
- `Block`/`Part` are `core.types` frozen dataclasses; `Part.values` is a tuple; `Blocks` is a tuple.
  Legacy mutated blocks in place (`set_seed`, `relevel`, `set_element`); transforms now return new tuples.
- Every failure is `SerialError` (legacy: `ValueError`, `TypeError`, `IndexError`, `AttributeError`).
- Legacy conveniences `decode_to_string` / `encode_from_string` are gone (compose the port methods).
  `encode_from_string` silently appended a missing final `|`; `encode` now refuses blocks that do not end
  with the terminator (see Strictness), so a caller parsing free text must make sure it ends with `|`.
- `get_manufacturer_index` is `get_category_id`; `_int_at_pos` is `int_at`; `set_seed` is
  `with_int_at(blocks, 5, seed)` (seed position 5 stays the caller's business: ops owns that constant).

**Strictness on input (legacy was lenient or silently wrong)**
- Foreign characters inside a serial are an error. Legacy skipped them (so `"@U...x..."` decoded) and
  crashed with `IndexError` on any character above U+00FF. Surrounding whitespace is NOT stripped.
- A dangling single base85 character, or a 5-character group that overflows 32 bits, is an error
  (legacy dropped / wrapped them).
- Bits left after the last token must be zero padding; the block list must end with the `|` terminator.
  Legacy returned a partial block list for ~20% of truncated serials (2,390 of 11,536 prefixes tried, on a 300-serial sample);
  now only prefixes that happen to end exactly on a `|` boundary (about 0.7%) get through. Cutting the
  last 1-3 characters of any database serial always raises.
- `encode` validates every block (known token, `Part` present, known subtype, value ranges, ASCII strings,
  terminator) before writing; legacy wrote garbage or raised `AttributeError`.

**Integer ranges (legacy silently corrupted)**
- Legacy masked values with `0xFFFFFFFF` but a nibble varint only holds 16 bits, and its token chooser
  never picked the 31-bit varbit above 65535: `relevel(s, 100000)` produced level 34464 and
  `set_seed(s, 2**32-1)` produced seed 65535, with no error. Now: values 0..65535 are encoded exactly as
  legacy; values 65536..2,147,483,647 are written as VARBIT, losslessly; anything else (negative, >= 2**31,
  `bool`, float, str, None) raises `SerialError`. Part indexes and integer-part values are limited to
  0..65535, part-list values to 0..2**31-1. Exposed as `CodecModule.MAX_INT_VALUE` / `MAX_PART_VALUE`.
- Real data stays far inside this: every plain integer block in the database is <= 4095 (levels are 30-50,
  seeds <= 4095).

**Text form (`parts_string` / `from_string`)**
- Strings: characters above 127 were masked to 7 bits on write (corruption); now `SerialError`. The
  `from_string` string scanner understands `\\` and `\"` properly, so every string round-trips (legacy
  mis-parsed a string ending in a backslash).
- Numbers in part lists must be plain ASCII digits (legacy `int()` accepted `-1`, `+3`, `1_0`, non-ASCII
  digits); more than 10 digits is rejected.
- `parts_string` raises `SerialError` for blocks it cannot print (unknown token, missing `Part`, unknown
  subtype) instead of silently skipping or printing `{ERR_UNKNOWN_PART:n}`.

**Unchanged on purpose (legacy quirks that real serials depend on)**
- Short final base85 groups are padded with the digit 126 (`~`) before masking to 32 bits.
- Non-canonical encodings (an over-long varint, a varbit with a leading zero) decode as legacy does;
  `encode` always writes the canonical form. Byte-identical round trip is therefore guaranteed for
  canonical serials, which is all 9,875 database rows.
- A tail of zero padding that reads as extra `|` tokens is trimmed to a single `|`.
- Bare `VARINT`/`VARBIT` text numbers choose the shorter token (VARBIT only when strictly shorter).

## Notes for callers (rules / ops / catalog / builder)
- Reach it with `self.dep("codec")` and declare `requires = ("codec",)` (or more). Stateless and
  thread-safe; about 0.1 ms per decode, no internal cache (cache decoded blocks yourself if you need to).
- Positions: `int_at` / `with_int_at` count only plain integer blocks (VARINT and VARBIT), in stream
  order; parts, strings and separators are not counted. Category id is position 0, the level marker is at
  2 (+ 2k), the seed is position 5 (the legacy `SEED_INT_POS`). `int_at` returns `None` past the end
  (and for negative positions); `with_int_at` raises `SerialError` there.
- To change anything else, slice the tuple: `blocks[:i] + (Block(...),) + blocks[i:]`. Index into `Blocks`
  is the `token_index` used by `PartRef`. Keep the final `|` block last or `encode` raises.
- `from_string` does not add a terminator; text must end with `|`, as `parts_string` output always does.
- `relevel(serial, level)` takes a serial string and returns a serial string; the level must be an `int`
  in 0..`MAX_INT_VALUE`. It raises `SerialError` if the serial has no level field; it never returns the
  original on failure (callers turn the error into a warning).
- Pass a `Blocks` tuple, never a serial string, to the block methods: a `str` raises `SerialError`.
- The database has duplicate rows: 9,875 rows, 8,520 distinct serials.

