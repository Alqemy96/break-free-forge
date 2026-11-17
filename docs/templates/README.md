# Save-format templates

This folder is a reference library of **reversed save formats**, written as
[ImHex](https://imhex.werwolv.net/) pattern files (`.hexpat`). Each template
records *structure*: field order, sizes, endianness, field names and how to
validate them. Games change between releases. Tools rot. A template written
down while a format is understood keeps the method alive for the next person
who opens a file they own.

> "You bought it, you should be able to open it." Everything here works
> offline, on your own files, and contains **no keys and no game data**.

## What a template is (and is not)

A template **is**:
- a byte-level map of a file: header, sections, trailers and padding
- documentation you can run, so opening a file in ImHex colours and names every region
- a place to write down validation rules ("FCHECK must be divisible by 31",
  "trailer equals inflated length")

A template **is not**:
- a decryptor. ImHex patterns cannot run AES, and we would not ship a key anyway.
- a container for real save bytes, real keys, key fragments, or anything that
  narrows the search for a key (no key hashes, no "key starts with...")
- a copy of game assets, string tables or other copyrighted data. Field
  *names* that appear in a save's own structure (for example YAML top-level keys)
  are structural facts and are fine. Bulk values copied out of a save are not.

## Using a template in ImHex

1. Install ImHex (free, open source, works offline).
2. Open the file you want to inspect (**File > Open File...**).
3. Load the pattern. Any of these works:
   - drag the `.hexpat` file onto the ImHex window, or
   - **File > Import > Pattern File...**, or
   - paste its contents into the **Pattern Editor** view and press the run button (F5).

   (Menu names vary a little between ImHex versions. UNVERIFIED against a specific release.)
4. The **Pattern Data** view lists every field. Clicking a field highlights its
   bytes. Comments appear as tooltips.
5. If a template has views or options, they appear in the Pattern Editor's
   **Settings** tab as input variables (`in` variables). Set them and re-run.

### Encrypted formats

ImHex cannot decrypt AES-ECB (or most game crypto) inline. Templates for
encrypted formats therefore describe the **decrypted plaintext**, and
optionally the ciphertext's block grid. The workflow is:

1. Decrypt your save with this repo's offline save tooling
   (`src/bl4forge/modules/save/`), using a
   key **you** recovered from your own console's memory dump with the method in
   [`docs/runbooks/ORACLE_COOKBOOK.md`](../runbooks/ORACLE_COOKBOOK.md).
   The repo never ships a key.
2. Open the decrypted file in ImHex with the template (container view).
3. To see the inflated body as well, inflate it with the standard library only:

   ```bash
   python -c "import sys,zlib; d=open(sys.argv[1],'rb').read(); o=zlib.decompressobj(); sys.stdout.buffer.write(o.decompress(d)); sys.stderr.write('trailer+pad: %d bytes\n' % len(o.unused_data))" plain.bin > save.yaml
   ```

   Then open `save.yaml` with the same template (it auto-detects the YAML view).

Recent ImHex versions also ship a `hex::dec::zlib_decompress` helper in the
pattern standard library that can inflate into a virtual section. The
templates here don't rely on it, for compatibility. UNVERIFIED which ImHex
version introduced it.

## Library index

| Game | Platform | Template | Notes | Status |
|---|---|---|---|---|
| Borderlands 4 | PS5 | `borderlands4_ps5.hexpat` | `borderlands4_ps5.md` | layout from repo CONTEXT. Template not yet test-loaded in ImHex |
| *Demo Game (fictional)* | n/a | `demo_game.hexpat` | `demo_game.md` | quality-bar example only |

## Contributing a new game

**One game/platform = exactly two files**, named `<game>_<platform>`, all lowercase, underscores:

```
docs/templates/<game>_<platform>.hexpat   # the pattern
docs/templates/<game>_<platform>.md       # short notes (aim for under a page)
```

Then add one row to the index table above.

### The `.hexpat` must

- start with the SPDX line (`AGPL-3.0-or-later`, the repo licence), a header
  comment naming the game, platform and game version(s) it was checked against,
  and `#pragma description` / `#pragma endian`
- give every field a meaningful name and a `[[comment(...)]]`
- mark each non-obvious field's provenance in its comment:
  - `[V]` verified: checked against at least two of *your own* files, or
    against working code in this repo
  - `[U]` unverified: inferred, guessed, or seen once
- use `std::assert` for hard invariants (sizes, magic, checksums it can
  compute) and `std::assert_warn` for soft expectations
- use `enum` / `bitfield` instead of bare integers when values are known
- be **data-only**: no keys, no key material, no embedded save bytes, no
  copied game data. Constants are allowed only when they are format facts
  (magic numbers, version numbers, header bytes of a public compression format).

### The `.md` must contain these sections, in order, kept short

1. **Format at a glance**: one diagram or formula of the on-disk layout.
2. **Validation**: how a tool knows a parse or decrypt succeeded.
3. **Encryption / compression**: algorithm names and modes only. If a key is
   involved, *describe the method* or link `ORACLE_COOKBOOK.md`. Never the key.
4. **Known unknowns**: everything marked `[U]`, as a list.
5. **Checked against**: game version(s), platform, date. No file hashes of real saves.

### Review checklist (reviewers tick these)

- [ ] two files, correct names, index row added
- [ ] loads in ImHex without errors on a real (private, not committed) file
- [ ] no keys, key fragments, key hashes, or turnkey extraction steps
- [ ] no real save bytes or copyrighted data in the template, notes or tests
- [ ] every `[U]` field also listed under **Known unknowns**
- [ ] `demo_game.hexpat` quality bar met (comments, asserts, enums, provenance)

See `demo_game.hexpat` for the expected standard.
