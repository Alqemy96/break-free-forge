# The scanner: how we got in, and why it matters

*You bought it. You should be able to open it.*

This is the page about the one idea the rest of the project stands on: **a game that hides your save behind a
fixed key hides it behind no secret at all.** The key is sitting in the game's own memory, every copy, every
launch, and a few minutes of brute force on a machine you already own is enough to find it. No disassembly, no
tracing the save routine, no reverse-engineering the publisher's code. Once you understand why, you can do it to
most games that seal their saves this way — and you can decide for yourself whether a thing you paid for is
really yours.

## The lock

Borderlands 4 stores each PS5 save as:

```
AES-256-ECB( PKCS7( zlib_stream || uint32_LE(uncompressed_length) ) )
```

AES-256 is strong. If the key were random and per-user, this would be the end of the road. But it is not: it is
a **single fixed 32-byte key, compiled into the game, the same for every copy of a given version.** The strength
of the cipher is irrelevant when the key ships inside the product that uses it. That is the whole weakness, and
it is a design choice many games make because it is cheap and stops the casual tinkerer.

## The idea

You do not need to find the key by reading code. You need only two things you already have the right to:

1. **A memory dump of the running game** — the bytes the game had loaded while you played your own copy.
2. **One encrypted save** of the same version — a file the game wrote for you.

The key is somewhere in that dump. You just do not know where. So you try **every** position: treat each byte
offset as the start of a candidate 32-byte key and test it. For a 100–200 MB dump that is one to two hundred
million candidates — a few minutes on an ordinary many-core PC, because testing one candidate is cheap.

## The oracle: how a candidate proves itself

The elegant part is that you never need to recognise the key by its shape. You let the data judge it. For each
candidate key:

1. AES-ECB **decrypt** the encrypted save with it.
2. Strip PKCS7 padding (or accept it unpadded if the payload is already block-aligned).
3. The result must be a **complete zlib stream that fully decompresses with no error**, and — if the trailer is
   present — the 4-byte length at the end must equal the size of what you just decompressed.

A wrong key turns the ciphertext into noise. Noise is not a valid zlib stream; it fails almost instantly. The
chance of random bytes decompressing cleanly *and* matching their own declared length is vanishingly small, so a
candidate that passes is the key. The first real run produced **exactly one hit.** No heuristics, no
key-schedule guessing, no false positives to sift.

That oracle is the engine. It is also what makes the tool honest: it cannot invent a key, it can only recognise
one that is already present in bytes you supplied.

## Writing the scanner

This repository publishes the **method, not a turnkey extractor**: it ships no key, no dump, no save, and no
ready-to-run scanner (see `SECURITY.md`). The scan is short enough to write yourself from the description above,
and writing it yourself is the point — the key to your saves should come from your game, found by you.

The shape of it:

```
for each byte offset in your-own memory dump:
    candidate = dump[offset : offset + 32]          # also try 16 for 128-bit schemes
    plain = aes_ecb_decrypt(candidate, your-own-encrypted-save)
    plain = strip_pkcs7(plain)                       # or accept it unpadded if block-aligned
    if zlib.decompress(plain) succeeds completely    # and, if present, the 4-byte LE trailer == its length:
        print(candidate.hex())                       # this is your key
```

Everything you need is stdlib except AES-ECB itself; a pure-Python AES-256 block implementation lives in this
tree at `src/bl4forge/modules/save/_aes.py` and can be imported or adapted. Run it in parallel across offsets
and a 100–200 MB dump finishes in a few minutes. It needs two files **you** supply — your dump and your
encrypted save — and nothing of its own; it recovers your key, never someone else's, and makes no network
connection.

## Why this is the point of the project

Everything else here — the save editor, the serial codec, the loadout builder — only works once a save is open,
and a save only opens once you hold the key. We did not publish the key, and we will not: a fixed key can be
rotated by the publisher, and more importantly, the key to your saves should come from your game, on your
hardware, found by you. What we publish is the **method**, so that the next person does not have to rediscover
it, and so that the knowledge of how these locks actually work belongs to the people who bought the games, not
only to the people who built the locks.

A fixed key is not security. It is a sticker that says "do not open." This tool reads the sticker.

## For the next game

The scanner is deliberately game-agnostic. If another title seals its saves with a fixed AES-ECB key over a
zlib (or similar) payload, the same two inputs and the same oracle will find its key too — the decompress-and-
check test is all that is specific, and it is easy to adapt. The deeper method (brute-scan a dump, let a
structural check on the plaintext confirm the key) applies to a wide class of schemes. `docs/runbooks/RESEARCHER.md`
has the format details and the open questions; this page is the why.

> **Ownership, not piracy.** This is for reading and editing **your own** saved game, offline. It is not a way
> around anyone's paid online service, and it will not help you touch another player's data. Decrypting a save
> you did not make is not what this is for.
