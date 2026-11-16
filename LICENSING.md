# Licensing

**The whole tree is licensed under the GNU Affero General Public License, version 3 only (AGPL-3.0-only).**
The full text is in `LICENSE`. Credits are in `NOTICE`.

## Why AGPL-3.0

The serial codec (`src/bl4forge/modules/codec/`) is a Python port of
[Nicnl/borderlands4-serials](https://github.com/Nicnl/borderlands4-serials), which is AGPL-3.0. Code derived
from it must be AGPL-3.0 too, so everything published here is AGPL-3.0. Section 13 of the AGPL applies if you
run a modified copy as a network service: you must offer its users the source.

## What you may do

- Use it, study it, change it, and share it, under the AGPL-3.0 terms: keep the license and notices, state your
  changes, and publish the source of what you distribute or serve.
- Reuse the codec or the save container in your own project only if that project is also AGPL-3.0-compatible.
  See `docs/runbooks/DEVELOPER.md`, "Reusing parts".

## What is not here, and not yours to assume

- **Game data.** Nothing extracted from the game (part tables, drop tables, paks, manifests) is included. It is
  Gearbox / 2K material. If you generate your own copy for private use, do not republish it.
- **The community serial database.** The database the catalog reads was scraped from community sources whose
  authorship and terms are unknown, so it is not included.
- **Keys.** No save-encryption key is included (see `SECURITY.md`).
- **Loot-pak tools.** The `lootpak` cell drives external programs you must supply. Those programs have their own
  licenses (the upstream `bl4` toolkit is BSD-2-Clause, see `NOTICE`). Anything the builder produces contains
  game data and is yours alone: do not share it.
- **Fonts and npm packages.** The `ui/` source lists its npm dependencies in `ui/package.json`; each keeps its own
  license. No built bundle is included.

## Trademarks

Borderlands and related names are trademarks of Gearbox Software and 2K. This project is unofficial and is
not affiliated with or endorsed by them.

## No warranty

See sections 15 and 16 of `LICENSE`. Editing a save can corrupt it. Back up first.
