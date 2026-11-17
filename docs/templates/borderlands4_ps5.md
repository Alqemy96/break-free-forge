# Borderlands 4 (PS5) save

Template: `borderlands4_ps5.hexpat` (views: 1 ciphertext, 2 decrypted container, 3 YAML).

## Format at a glance

```
.sav = AES-256-ECB_k( zlib(YAML) || u32le(len(YAML)) || PKCS7_pad )
                                                         ^ 1..15 bytes, or none if
                                                           the payload is already
                                                           a multiple of 16
```

The YAML is UTF-8, about 26 KB. Top-level keys used by the repo's save code and synthetic
fixtures: `state`, `stats`, `progression`, `domains`. Also listed by the template but
UNVERIFIED (not seen anywhere in the repo): `onlinecharacterprefs`, `pips`, `globals`,
`activities`, `missions`, `save_game_header`, `timed_facts`.

## Validation

A decrypt is correct when the plaintext starts with a **complete** zlib stream
and the 4-byte LE trailer right after it equals the inflated length. Try
**padded first** (strip PKCS7), then **unpadded**. Both cases use the same
zlib + trailer check. The YAML itself carries no checksum.

Layout-only shortcut (the template uses it): with the length under 16 MiB, the
payload's last byte is `0x00`, so a final `0x00` means unpadded and a final `n`
(1..15) repeated `n` times means padded.

## Encryption / compression

- AES-256 in ECB mode. One fixed 32-byte key compiled into the game.
- **Key:** never published here. The *method* (scan your own memory dump with
  stride 1, try every 32-byte window, keep the one whose decrypt passes the
  validation above) is in `docs/runbooks/ORACLE_COOKBOOK.md`.
- zlib (RFC 1950) wrapping DEFLATE (RFC 1951). The game writes header `78 9c`; this repo
  writes `78 da` (level 9), which the console accepts (`_container.py`, `ZLIB_LEVEL`).
- The game re-serializes on every load, so byte diffs between saves are noisy.
  Compare the inflated YAML semantically.

## Known unknowns

- Order of the top-level YAML keys, and whether other keys appear in some saves.
- Whether the YAML starts with `---` or comment lines.
- Upper bound on the uncompressed length (the template warns above 16 MiB).
- Template not yet loaded in a real ImHex build.

## Checked against

Layout checked against `src/bl4forge/modules/save/_container.py` and
`docs/runbooks/RESEARCHER.md` (2026-11-17). Game version / firmware: to be filled in by the
first contributor who test-loads the template.
