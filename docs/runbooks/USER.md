# User runbook: get it running and edit a save safely

Read `DISCLOSURE.md` first if you want to know exactly what the program does. Short version: it works on
**files you give it**, never opens a network connection, and never modifies the save you point it at.

## Golden rules

1. **Close the game before you write.** A running game holds its save and re-writes it. Never copy an edited
   save over the live one while the game (or the console's save service) is running.
2. **Work on copies.** Keep an untouched original somewhere safe (and record its sha256: the tool does this for
   you in the `.bl4forge.json` sidecar). The tool refuses to write over the file you read from.
3. **The game re-writes the save every time it loads one** (same values, different bytes). After you have
   started the game with any save, do not reuse an edit you made before: re-copy the current save and edit that.
4. **One change at a time.** Make an edit, test it in game, then make the next. If something breaks you will
   know which edit did it.
5. **Never share a save, a decrypted YAML, or your key.** They contain account-bound data.
6. Online play with an edited save can have consequences from the publisher. That risk is yours.

## 1. Install

Needs Python 3.10 or newer. In the project folder:

```
python -m pip install -e .[dev]
python -m pytest -q
python -m bl4forge doctor
```

The test run should finish with passes and skips and no failures. Many tests are skipped because they need game
data you have not supplied; that is expected. `doctor` reports each module; `catalog` and `data` show
"degraded" until you supply data, which only affects name lookups and searching, not saves.

## 2. Configure

Copy `config.example.toml` to `config.toml` (it is git-ignored) and edit:

- `[save] ps5_key` : the 64-hex-digit AES-256 key of the PS5 game layer. **This project does not ship it and does
  not explain how to find it. You must obtain it yourself.** Leave it empty and PS5 saves will not open
  (a clear "key missing" message names the setting). Never paste the key into an issue, a chat, or a commit.
- `[save] pc_base_key` : only for PC saves (with `--platform pc --steam-id <your id>`).
- `[forge]` / `[ownership]` : defaults for searches and builds. Optional.

## 3. Get a save file

This project ships **no** console transfer tool. Use your own save-transfer homebrew or the platform's own
export to get `gbxsavegame.sav` (PS5, already stripped of the console's outer layer) or your PC `.sav` onto the
computer, and use your own method to put the edited file back. Warnings:

- Transferring saves can write to the console's storage. Make your own backup first, with the game closed.
- Some transfer tools mount the save read-write and change it even when you only "export". Check the tool's
  behavior and keep a verified backup of everything it touches.
- Keep the console offline for experiments if you can; do not use these tools with anyone else's account.

Put your original in a folder such as `saves/original/` and never edit it.

## 4. Look at the save (read only)

```
python -m bl4forge save-open  --file saves/original/gbxsavegame.sav
python -m bl4forge save-items --file saves/original/gbxsavegame.sav
```

PC saves: add `--platform pc --steam-id <digits>`. These commands read the file and write nothing.

## 5. Decrypt a COPY to YAML (optional, for reading)

```
python -m bl4forge save-decrypt --file saves/original/gbxsavegame.sav --out work/save.yaml
```

The YAML contains your character name and account-bound data: do not share it.

## 6. Edit

Every edit command writes a new copy and a sidecar, never the original. Use `--dry-run` first: it shows the
exact lines that would change and writes nothing.

```
python -m bl4forge save-set-currency --file saves/original/gbxsavegame.sav --name eridium --value 5000 --dry-run
python -m bl4forge save-set-currency --file saves/original/gbxsavegame.sav --name eridium --value 5000 --out work/edited.sav
python -m bl4forge save-set-level --file saves/original/gbxsavegame.sav --level 70 --out work/edited.sav --overwrite
python -m bl4forge save-set-serial --file saves/original/gbxsavegame.sav --ref backpack/slot_3 --serial "<serial>" --out work/edited.sav
```

Each edit changes exactly one existing line of the YAML. It never inserts or deletes lines. Chaining edits:
use the previous output as the next `--file` (so every step stays a copy of a copy), or apply several edits at
once through the web UI.

Facts worth knowing:

- Level: the game may re-derive level from XP points. Set `--xp` as well when raising level (see
  `docs/runbooks/RESEARCHER.md` for the XP curve found so far).
- Items: the serial you set must decode. "Decodes" does not mean "the game keeps it": test one item first.
  Re-leveling a serial you know is good (`relevel`) is the safest way to get a high-level item.
- Profile saves have separate edits (`save-set-point-pool`) and are less explored.

## 7. Verify before you use it

The edit command re-reads the copy it wrote and proves it decrypts to exactly the edited text. You can check
again yourself:

```
python -m bl4forge save-open --file work/edited.sav
```

and compare `work/edited.sav.bl4forge.json` (the original's sha256, the copy's sha256) with your own
`sha256sum` of the original: the original's hash must not have changed.

## 8. Put it back (with your own tool)

1. Close the game completely (not suspended / rest mode).
2. Back up the live save with your transfer tool.
3. Replace the save with `work/edited.sav` using your own tool.
4. Start the game and check the change. Note that the game rewrites the save on load.

## 9. Undo

Put the backup of the live save back the same way (game closed). Because the tool never touched the original,
you can also simply re-copy the original and redo your edits from step 6.

## The web UI

```
cd ui && npm install --include=dev && npm run build     # builds into src/bl4forge/web/static/
python -m bl4forge serve --open
```

It listens on `127.0.0.1:8734` only and has no login. Do not use `--allow-remote`. The server never writes a
file: the save endpoints return the bytes and your browser saves them as a copy.

## If something goes wrong

- `key missing`: set `[save] ps5_key` in `config.toml`.
- `bad padding` / `zlib` error: wrong key, wrong platform, or the file still has the console's outer layer.
- `required data is missing`: you used a command that needs the game data or serial database; supply your own
  (see `docs/runbooks/DEVELOPER.md`, "Supplying data") or use commands that do not need it.
- Run `python -m bl4forge doctor -v` and `--debug` for details. Do not post saves or keys when you ask for help.
