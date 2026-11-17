# Oracle Cookbook

**Runbook:** `docs/runbooks/ORACLE_COOKBOOK.md`
**Audience:** someone porting the Break Free Forge brute-scan method to a game they own
**Status labels:** **proven** = done and reproduced in this repo · **recorded** = from the public
community record, not reproduced here · **UNVERIFIED** = reasoned or remembered, not checked against a
primary source

> This runbook documents a *method*. It contains no keys, no key fragments and no turnkey extractor,
> and it never will. Everything here runs offline, on a memory dump and save files you made yourself.

---

## 1. What an oracle is

The brute-scan method has three slots. Only the third one changes from game to game.

| Slot | What it is | Changes per game? |
|---|---|---|
| **Input** | One memory dump of the running game, plus one encrypted save from the same console/account. | No |
| **Scan** | Stride 1 over every byte offset in the dump. Each 32-byte (or N-byte) window is a candidate key. | Only the window size and cipher |
| **Oracle** | A structural check on the candidate plaintext that answers "is this a real decrypt?" with yes or no. | **Yes** |

The **oracle** is the check that tells a correct decryption from noise. Wrong keys produce
uniformly random-looking plaintext. The right key produces *structure*. The oracle's job is to
recognise that structure **cheaply** (it runs hundreds of millions of times) and **precisely**
(a false positive wastes your afternoon; a false negative makes the scan miss the key).

A good oracle is:

1. **Cheap to reject early.** Check the first block before decrypting the rest. With ECB, every
   block decrypts on its own, so you can test block 0 alone. (proven: BL4)
2. **Specific.** The chance of a random plaintext passing it must be tiny (see §4).
3. **Independent of the key.** It checks properties of the plaintext format, never a known key value.

---

## 2. Decision table: plaintext feature → oracle check

Work out what the decrypted save probably *looks like* (from PC saves, older platform versions,
decompiled loaders or community notes), then choose checks from this table. Stack two or more.

| Plaintext feature | Oracle check | Early-reject cost | Strength | Notes |
|---|---|---|---|---|
| **zlib stream** (`78 01` / `78 5E` / `78 9C` / `78 DA`) | byte 0 = `0x78` and `(b0·256 + b1) % 31 == 0`, then `zlib.decompressobj()` runs to `eof` | 1 block | Strong (header ≈ 1/7,936; full inflate much stronger) | proven: BL4 |
| **gzip** (`1F 8B 08`) | 3-byte magic, then `gzip.decompress` succeeds | 1 block | Strong (magic alone ≈ 1/16.7M) | Also check the CRC32 + ISIZE footer |
| **zstd** (`28 B5 2F FD`) | 4-byte magic, then frame decodes | 1 block | Strong (≈ 1/4.3B on magic) | Not in the stdlib, so do the magic check in stdlib and decode as an optional extra |
| **lz4 frame** (`04 22 4D 18`) | 4-byte magic + header checksum byte | 1 block | Strong | Raw LZ4 blocks have no magic, so they are **weak** |
| **Magic bytes at a known offset** (e.g. `SVCS` at 0x10 in MGSV, `PSIN` in RAGE PSO blocks) | `pt[off:off+4] == magic` | 1–2 blocks | Medium–strong (2⁻³² per 4-byte magic) | MGSV is recorded; the RAGE `PSIN` offset is UNVERIFIED |
| **Length field / trailer** (e.g. `uint32_LE(uncompressed_len)`) | field equals the observed size (or the size inflate actually produced) | last block | Strong (≈ 2⁻³²) | proven: BL4 trailer |
| **Checksum** (adler32, CRC32 and its variants, Jenkins one-at-a-time "joaat", FNV-1/1a) | recompute it over the declared span and compare it to the stored field | full decrypt | Very strong (≈ 2⁻³² each) | You need the span and the seed, so get them from known plaintext first. CRC variants differ in poly, init, reflect and xorout (UNVERIFIED per game) |
| **Text serialization** (YAML / JSON / XML) | valid UTF-8, then printable-ratio > 0.95, then the parser succeeds | 1 block for ASCII-ness, full for the parse | Medium on its own, strong once parsed | BL4 plaintext is UTF-8 YAML (proven) |
| **Binary struct layout** | plausible field ranges (version is small, counts < size, offsets in bounds) | 1–2 blocks | Weak–medium | Good as a *second* check, never the only one |
| **Known plaintext** (player name, GUID, timestamp near the save's mtime) | substring / range match | full decrypt | Strong if the value is ≥ 8 bytes and unique | Only works on saves *you* made, which is the point |
| **Padding** (PKCS#7) | last byte n ∈ 1..16 and last n bytes all equal n | last block | Weak (≈ 1/256) | Never use it alone. BL4 is sometimes unpadded (see §3a) |

**Rule of thumb:** use one cheap check on the first block as a filter, then one or more strong
checks on the whole decrypt as confirmation.

---

## 3. Worked examples

### 3a. Borderlands 4, PS5 (proven, our own case)

**Format** (see `src/bl4forge/modules/save/_container.py` and `docs/runbooks/RESEARCHER.md`):

```
ciphertext = AES-256-ECB( PKCS7?( zlib_stream || uint32_LE(uncompressed_length) ) )
```

PKCS#7 padding is applied **except** when the payload is already a multiple of 16 bytes. In that
case there is no padding at all.

**Oracle used**, in order of cost:

1. **Block-0 filter:** `ecb_decrypt(candidate, block0)` → byte 0 == `0x78` and `(b0<<8 | b1) % 31 == 0`.
   This rejects about 99.99% of candidates after one AES block.
2. **Full decrypt**, trying *padded first*: strip PKCS#7 if the padding is valid, otherwise fall
   back to *unpadded*.
3. **Inflate:** `zlib.decompressobj().decompress(body[:-4])` must reach `eof`, with nothing left
   in `unused_data` before the trailer.
4. **Trailer:** `struct.unpack('<I', body[-4:])[0] == len(inflated)`.
5. *(Optional sanity check)* `inflated.decode('utf-8')` succeeds and looks like YAML (about 26 KB).

Checks 3 and 4 are independent, so together they are what make the result definitive (see §4).
Both padding branches are validated by the *same* zlib + trailer test, which is why the
padded/unpadded ambiguity is harmless.

Implementation notes for this repo:

- Reuse `_aes.expand_key` and `_aes.ecb_decrypt(key, data)` from `src/bl4forge/modules/save/_aes.py`.
  Do not write a second AES. `ecb_decrypt` expands the key itself on every call.
- Key expansion dominates the per-candidate cost. Do the block-0 filter with a single-block
  decrypt (`ecb_decrypt(candidate, ciphertext[:16])`) before decrypting anything else.
- The full check in steps 2-4 is exactly what `_container.decrypt(data, key, "ps5")` does; call it
  for confirmation instead of re-implementing it.
- Run `_aes.known_answer()` once at startup so a broken AES can't silently miss the key.
- Never print the winning key. Report the **dump offset** only, and let the user decide what to do
  with their own memory.

### 3b. Metal Gear Solid V (recorded, precedent)

From the public modding record: MGSV save files were obfuscated with an XOR stream. The community
recovered the stream's initial value by brute force, testing candidates until the decrypted
data showed the **`SVCS` magic at offset 0x10**. The value later turned out to be derived from the
**MD5 of the save folder name**, not a secret.

Why it matters here:

- It is the same **scan → oracle** shape: enumerate candidates, accept the one that produces a
  fixed magic at a fixed offset. That shape was established in the community before Break Free
  Forge existed. We generalise it; we did not invent it.
- It shows a single 4-byte magic working as the oracle (§2: medium–strong). It was enough there
  because the candidate space was small.
- It is a reminder that a "key" is often *derived* from something you already own (a folder name,
  an account ID). Look for a derivation before reaching for a memory dump.

**UNVERIFIED:** the exact cipher details (stream construction, which bytes are XORed, whether the
MD5 input is the folder name exactly as written) were not reproduced in this repo. Cite the original
community write-up before relying on them.

---

## 4. False-positive math

Let **N** = number of candidates. Stride 1 over a 200 MB dump gives **N ≈ 2.1 × 10⁸**.
A wrong key yields effectively random plaintext, so a check with pass probability **p** produces
about **N·p** false positives. Independent checks multiply.

| Oracle | p (random plaintext) | Expected false positives, N = 2.1×10⁸ |
|---|---|---|
| zlib header only (`0x78` + mod-31) | ≈ 1/7,936 | **≈ 26,000** (useless on its own) |
| PKCS#7 looks valid | ≈ 1/256 | ≈ 820,000 |
| one 4-byte magic | 2⁻³² ≈ 2.3×10⁻¹⁰ | ≈ 0.05 |
| 4-byte length trailer | 2⁻³² | ≈ 0.05 |
| zlib header **and** trailer | ≈ 2.9×10⁻¹⁴ | ≈ **6×10⁻⁶** |
| header + full inflate to `eof` + trailer (BL4) | far smaller (inflate rarely survives random input) | **effectively 0** |

**Takeaway:** a single 4-byte check is *probably* fine. **Two or more independent structural checks
push expected false positives over a 200 MB dump to effectively zero**, and that is the standard
this repo uses. "Independent" means one check must not imply the other. For example, a trailer
plus a CRC over the same field is a single check, not two.

*Caveat (UNVERIFIED in general):* dumps contain many non-random windows (runs of zeros, pointer
tables). Those windows are not uniformly random keys. They can't make a *structural* oracle pass
any more easily, but they can make cheap filters like the printable-ratio check fire more often
than the math above predicts. Always confirm with a strong check.

---

## 5. Adapting to a new game in 10 steps

1. **Ownership check.** You own the game and the console/PC. The dump and the save are yours, and
   everything stays offline. If any of that is not true, stop.
2. **Make a fresh save, then dump.** Save in game, then take a memory dump while the game is
   still running. Keep the pair together and note the time.
3. **Find the cipher and block size.** Is the size a multiple of 16 (AES/ECB)? Do any 16-byte
   blocks repeat (an ECB tell)? Is there a header in the clear? Write down what you find, and
   label anything you guessed as UNVERIFIED.
4. **Guess the plaintext format.** Look at PC or older saves, string tables in the executable,
   and community notes. Expect compression, magic bytes, text, or a struct.
5. **Choose a block-0 filter** from §2, one that needs only the first block (a compression
   header or a magic in bytes 0–15).
6. **Choose at least one strong confirmation check** that is independent of the filter: a
   length/trailer, a checksum, a full decompress, or a parse plus known plaintext.
7. **Do the math (§4)** for your dump size. If expected false positives are ≥ 0.01, add another
   independent check.
8. **Test the oracle without a key.** Run it on random bytes (it must reject everything) and on
   a known-good plaintext you built by hand (it must accept it). An oracle you haven't tested
   is how a scan misses the right key.
9. **Run the scan** with the repo's AES, `known_answer()` first, stride 1, and a progress
   readout. Record the **offset** of any hit, never the key bytes.
10. **Close the loop.** Decrypt, edit one harmless field, re-encrypt, and load it in the game. Then
    write a runbook entry using the proven / recorded / UNVERIFIED labels, with no key material.

---

*No keys appear in this document. If a review ever finds one in this file, a fixture or a
commit, treat it as a bug: remove it and rewrite history.*
