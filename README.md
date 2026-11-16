# Break Free Forge

*You bought it. You should be able to open it.*

## Why

Borderlands has always been about breaking free: from the corporations that run Pandora, Kairos and every
planet in between. This project carries that idea off the screen.

- **Ownership.** A console you paid for, and a save file you built by playing, should be yours to read, back up
  and change. This repository shows how far one player got doing exactly that, on a PS5 copy of Borderlands 4.
- **Standing on the scene's shoulders.** None of this exists without years of open console research by people
  who published their work instead of locking it away. Credit flows back to them (see `NOTICE`), and these
  findings go back out the same way.
- **A new kind of workshop.** Most of this was built by one player working alongside an AI. The save format,
  the loot tables, the level curve and item editing fell in days, not years. The frontier moved, and it is open
  to anyone willing to learn.
- **Honest about the limits.** What failed is written down next to what worked, because the next person can
  only push further from the truth.

Breaking free here means owning and modifying **your own copy, offline**. It does not mean piracy, cheating
against other players, or getting around anyone's paid online services, and this project will not help with
those.

A local-first, offline toolkit for **Borderlands 4**: an item-serial codec, a save-file container (PS5 and PC
layouts), a line-level save editor that only ever writes a copy, a searchable catalog and loadout builder, a
local web UI, and an experimental loot-table pak builder. Pure Python standard library (the UI is React, built
separately).

> **Unofficial.** Not affiliated with or endorsed by Gearbox Software or 2K. Editing saves can corrupt a
> character and may have consequences if you play online. Back up first. AGPL-3.0-only, see `LICENSING.md`.

## What this public copy contains, and what it does not

Included: the Python package (`src/bl4forge`), its tests, the web UI **source** (`ui/`), example loot-pak
configs, and the documentation.

Not included, on purpose (see `SECURITY.md`): any game data or extracted tables, the community serial database,
any save file, any key (the PS5 save key is **not** here and this project does not ship it; `docs/runbooks/RESEARCHER.md` describes the general method only),
console transfer tools, and cheat or code-patch tooling. Commands that need the game data or the serial
database tell you plainly that you must supply your own; commands that do not need them (serial decode,
encode, re-level, and save editing once you have a key) work out of the box.

Read `DISCLOSURE.md` for exactly what every command reads, writes, and whether it touches the network.
(Short answer: it never makes an outbound connection; the web UI listens on `127.0.0.1` only.)

## Status

Early, working, and honest about what is proven. Tested on **Borderlands 4, PS5, version 01.100.002**. "Proven"
below means it was tried in the real game by the maintainer; everything else is unproven.

### Proven in game (PS5, BL4 01.100.002)

- **Save decrypt / edit / re-encrypt.** The PS5 game layer of `gbxsavegame.sav` is decrypted, edited as text,
  re-encrypted and loads in game. Re-encrypting the unmodified text reproduces a loadable save; the game accepts
  our compressor's output.
- **Character level raised to 70.** Works (see `docs/runbooks/RESEARCHER.md` for the details and caveats).
- **Items.** Replacing item serials in a save works; an item at level 70 is accepted after re-leveling a known
  serial.
- **Cosmetics unlock list.** Editing the profile save's unlock list (profile unlockables, not the `pips_list`
  "new" markers) unlocked cosmetics.
- **Currency edits** (cash, eridium) in a character save.

### Tried and did not work, or is unexplained

- **Loot paks (loot-table value edits):** results are **mixed and unexplained**. Some builds visibly changed
  drops; a later build with larger values produced no gear in 20+ kills, and a build that differed from the
  earlier good one only in an unrelated table showed the same loss. Drop variance or an install-related effect
  is possible; the cause is not established.
- **Solo spawn-table edit:** no visible effect on enemy counts.
- **A loot-luck code patch:** showed no effect. (That tooling is not part of this project.)
- Unverified: which flag gates the higher difficulty mode, how stat ranking of items works, whether the game
  derives level from XP after a level-only edit. See the open questions in `docs/runbooks/RESEARCHER.md`.

## Quick start

```
python -m pip install -e .[dev]
python -m pytest -q              # data-dependent tests skip cleanly without your data
python -m bl4forge --help
python -m bl4forge decode --serial "<a serial you own>"
python -m bl4forge doctor
```

Python 3.10 or newer (3.11+ has `tomllib`; 3.10 installs `tomli`). To edit a save safely, follow
`docs/runbooks/USER.md`.

## Documentation

| Read | For |
|---|---|
| `docs/runbooks/USER.md` | get it running and edit a save safely, step by step |
| `docs/runbooks/DEVELOPER.md` | architecture, adding a module, tests, the loot-pak builder, reusing the codec |
| `docs/runbooks/RESEARCHER.md` | the save format, the loot-table findings, open questions |
| `docs/ARCHITECTURE.md`, `docs/WEB_API.md` | the cell mesh and the local JSON API |
| `DISCLOSURE.md` | what each command reads, writes, and contacts |
| `SECURITY.md` | reporting issues; what is intentionally not included |
| `LICENSING.md`, `NOTICE`, `LICENSE` | AGPL-3.0-only, credits |

## Layout

```
src/bl4forge/core/       shared types, vocabulary, ports (interfaces), registry, doctor
src/bl4forge/modules/    codec data rules ops catalog builder render save lootpak (one cell each)
src/bl4forge/cli/        the command line (outer layer)
src/bl4forge/web/        local web server (outer layer)
ui/                      web UI source (React + Vite); build it yourself
tests/                   pytest suite
examples/lootpak/        example loot-pak configs
```
