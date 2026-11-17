# Demo Game (FICTIONAL)

Template: `demo_game.hexpat`. This game and format do not exist. Use this
pair as the model for real contributions.

## Format at a glance

```
Header(20) | SectionEntry[section_count](20 each) | payloads | Footer(8, optional)
```

## Validation

Magic `DMSV` at 0. Every section entry's `offset + size` is within the file.
If `has_footer`, the footer magic is `DEND` and `total_size == file size`.
Per-section CRC-32 is checked by tooling, not by the template.

## Encryption / compression

None at file level. Sections may be zlib (`compression == 1`). Inflate
outside ImHex. (A real encrypted game would name the cipher and mode here
and link `docs/runbooks/ORACLE_COOKBOOK.md` for the key-recovery *method*.)

## Known unknowns

- `big_sections` is always 1 so far, and its meaning is unconfirmed.
- `saved_at` might be local time rather than UTC.
- `currency` signedness.
- `slot == 0xFFFF` meaning.
- `HeaderFlags.reserved` bits.

## Checked against

n/a (fictional).
