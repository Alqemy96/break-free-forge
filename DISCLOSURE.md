# Disclosure: what each command does

Plain statement of what the code reads, writes and contacts. The same facts are in the header of every command
module (`src/bl4forge/cli/`) and every module `__init__.py`. If this file and the code ever disagree, the code
wins and this file is a bug: please report it (see `SECURITY.md`).

**Network.** The only network code in the tree is the local web server (`src/bl4forge/web/_server.py`), which
*listens* on `127.0.0.1` and makes no outbound connection. `serve --open` asks the operating system to open the
local URL in your browser. Nothing else opens a socket, sends or fetches anything, or phones home.
(`SECURITY.md` lists the grep that backs this.)

**Code execution.** The program never evaluates text from files or the network (`eval`, `exec`, `pickle`,
`marshal` and shell strings are not used). The one place it starts another program is `lootpak-plan` /
`lootpak-build`, which runs the executables named in your own `config.toml` as an argument list, never through
a shell.

| Command | Reads | Writes | Network | Risk / warning |
|---|---|---|---|---|
| `catalog` | `<data_dir>/bl4-serial-matches.json` (you supply it) | nothing | none | none |
| `search` | the same database, plus `<data_dir>/manifest/` | nothing | none | none |
| `decode` | the serial you pass | nothing | none | none |
| `relevel` | the serial you pass | nothing (prints a new serial) | none | the new serial is only structurally checked, not proven in game |
| `identify` | the serial; manifest if present | nothing | none | none |
| `set-element` | the serial; manifest if present | nothing (prints a new serial) | none | does not check the item is a weapon; result is only structurally checked |
| `reseed` | the serial | nothing (prints a new serial) | none | as above |
| `diff` | two serials | nothing | none | none |
| `swap` | two serials; manifest if present | nothing (prints a new serial) | none | refuses cross-category swaps unless `--allow-cross`; finer part compatibility is not enforced, so a result may not be valid in game |
| `validate` | the serial; manifest if present | nothing | none | "structurally valid" is not "works in game" |
| `build` | a `--spec` file (JSON) or inline JSON; database and manifest | the HTML sheet at `--out` and the text list at `--plain` (default: `--out` with `.txt`) | none | OVERWRITES those two files if they exist; the HTML is self-contained (no scripts, no external links) and escapes all text |
| `save-open` | the save at `--file` (read only) | nothing | none | prints your decoded save (character name, items); do not paste it into public places |
| `save-items` | the save at `--file` | nothing | none | as above |
| `save-decrypt` | the save at `--file` | the decrypted YAML at `--out` (refused if it is the source; refused if it exists without `--overwrite`) | none | the YAML holds account-bound data; do not share it |
| `save-set-currency` | the save at `--file` | an edited COPY at `--out` plus `<out>.bl4forge.json` (original's sha256). `--dry-run` writes nothing | none | never modifies the original; a bad edit can still corrupt the character. Close the game before copying it back; keep a backup |
| `save-set-point-pool` | a PROFILE save at `--file` | edited copy + sidecar, as above | none | in-game effect not verified; same warnings |
| `save-set-level` | the save at `--file` | edited copy + sidecar | none | the game may re-derive level from XP; see `docs/runbooks/RESEARCHER.md` |
| `save-set-serial` | the save at `--file` | edited copy + sidecar | none | the serial must decode, but "decodes" is not "the game keeps it" |
| `lootpak-plan` | a loot-pak TOML and the base game files it names; `config.toml [lootpak]` | scratch folder (deleted after) | none | RUNS the external tools from your config (see below) |
| `lootpak-build` | as above | a NEW folder `OUTDIR` only; refuses the base folder, a non-empty or `outN` folder, and anything under a `backups` folder | none | RUNS external tools; output is game data (a pak) whose in-game effect is unproven; never share it |
| `serve` | built UI files in `src/bl4forge/web/static/` (if built); whatever the browser posts | nothing to disk (save endpoints return bytes to the browser) | listens on `127.0.0.1:8734` only. A non-loopback `--host` is refused unless you also pass `--allow-remote` | no login. With `--allow-remote` anyone who can reach the port can use the save decrypt/encrypt service. Host and Origin checks refuse other names, but do not rely on them for exposure |
| `doctor` | nothing beyond the files the modules look for | nothing | none | none |

Where the `Reads` column says "manifest", that is the game-data folder `<data_dir>/manifest/`, which you supply.
Without the data files the commands that need them print a clear "data is missing, supply your own" message and exit 4.

## Environment and files that influence behavior

- `config.toml` (or `--config PATH`, or `$BL4FORGE_CONFIG`): defaults, the save keys, and the loot-pak tool
  paths. Treat it as executable configuration: a config someone else wrote could point `[lootpak]` at a
  program you did not choose. Never run with a config you did not write or read.
- `$BL4FORGE_ROOT`: overrides where the project root is looked up.
- `$BL4FORGE_SAVE_FIXTURES`: tests only; folder of your own save copies for optional tests.

## Modules (cells)

| Module | Reads | Writes | Network |
|---|---|---|---|
| `codec` | nothing | nothing | none |
| `data` | `<data_dir>/manifest/` | nothing | none |
| `rules`, `ops`, `builder` | nothing (use neighbours) | nothing | none |
| `catalog` | `<data_dir>/bl4-serial-matches.json` | nothing | none |
| `render` | nothing | `write()`: the two output files (overwrites) | none |
| `save` | the save passed to `write_copy` | edited copy + sidecar only; never the source | none |
| `lootpak` | loot-pak TOML, base files | scratch, then a new output folder | none; runs external tools |
