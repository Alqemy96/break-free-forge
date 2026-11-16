# Developer runbook

## Architecture: cells, ports, forge

The program is a **mesh of cells**. Each capability is one module ("cell") in `src/bl4forge/modules/<name>/`:

```
codec      serial <-> bitstream blocks            (pure)
data       the game's manifest tables             (read-only lookups; needs YOUR data)
render     Loadout -> HTML / text                 (pure, writes only the files it is told to)
save       PS5/PC .sav <-> YAML, line patches, copy-only writes   (leaf; keys from config)
rules      ownership + structural validation      <- codec, data
ops        identify / element / seed / swap / diff <- codec, data, rules
catalog    searchable serial database             <- codec, data, rules, ops   (needs YOUR database)
builder    requests -> verified Loadout           <- catalog, ops
lootpak    loot-pak builder from a TOML config    (leaf; runs external tools)
cli, web   outer layers that use a Forge
```

- **Port** = the interface a cell implements, a `Protocol` in `src/bl4forge/core/ports.py`. The doctor checks
  the method and parameter names match.
- **Forge** (`core/forge.py`) starts the cells in dependency order. A cell that fails to start is `failed`;
  cells that need it are `blocked`; the rest keep working. `Forge.build(overrides={"data": Fake})` swaps a cell
  for tests.
- **Fixed ports between cells.** A cell sees only the neighbours it lists in `requires`
  (`ModuleContext.dep()` refuses anything else), so a broken cell can be fixed alone.
- `core/` holds shared types, the one vocabulary (`vocab.py`: elements, rarities, characters), errors and the
  doctor. No module logic lives there.
- Each module has a `CONTRACT.md` stating its purpose, invariants (each has a test) and what is not verified.
  `docs/ARCHITECTURE.md` has the rationale; `docs/AGENT_RULES.md` has the rules each module follows.

## Rules every module follows (short)

1. Own one directory and its tests. Do not edit another cell.
2. Implement the port exactly. Reach neighbours only through `self.dep("name")`.
3. Shared things live in `core/`. Raise `ForgeError` subclasses, not bare `ValueError`.
4. No module-level mutable state; per-instance caches only.
5. Standard library only in `src/` (tomli on 3.10 for config).
6. Honest `health()`: fast known-answer checks, never raises.
7. **Network and execution are disclosed.** No socket, http, subprocess or file-writing code may be added
   without updating the `DISCLOSURE` header of that module and `DISCLOSURE.md`. Do not add outbound network
   code at all.

## Adding a module

1. Add `PortName` to `core/ports.py` and register it in the `PORTS` dict.
2. Create `src/bl4forge/modules/<name>/__init__.py` with a `Module` subclass setting `name`, `purpose`,
   `requires`, `port`, a real `health()`, and `MODULE = YourClass`. Put the **DISCLOSURE** block at the top of
   the docstring (reads, writes, network, risk).
3. Add the name to `MODULE_NAMES` in `src/bl4forge/modules/__init__.py`.
4. Write `CONTRACT.md` beside it and tests in `tests/modules/test_<name>.py`. Tests first.
5. If the CLI uses it, add a command in `cli/_commands.py` (or a new `cli/_<x>_cmds.py` with a DISCLOSURE
   header), declare which modules it `needs` in `cli/_parser.py`, and add the row to `DISCLOSURE.md`.
6. `python -m bl4forge doctor` must show it `ok` with no contract problems.

## Tests

```
python -m pip install -e .[dev]
(cd ui && npm ci && npm run build)   # the web tests serve the built UI bundle
python -m pytest -q
```

- Build the UI first: it writes `src/bl4forge/web/static/` (git-ignored). Without it the web tests that
  serve the default bundle fail with 404.
- Built-in test serials in the `_known.py` files are public community codes, kept as known answers.

- Standard library plus pytest. No network. No game, console, or save file is needed.
- Tests that need the user-supplied data or the (unshipped) legacy parity oracle **skip cleanly**; see
  `tests/conftest.py` (the `forge`/`legacy` fixtures and `_NEEDS_REAL_DATA`). With no data the suite finishes
  with passes and skips and no failures. With your own data more tests run.
- Tests use throwaway keys (`tests/save_helpers.py`), never a real game key. Do not add a real key, save, or
  account value to a test, fixture or doc.
- Optional real-save tests read `BL4FORGE_SAVE_FIXTURES` (a folder of your own save copies) and need your key
  in `config.toml`.
- Web tests start a real server on `127.0.0.1:<free port>` and talk to it with `http.client`.
- UI: `cd ui && npm install --include=dev && npm test` (vitest, pure logic) and `npm run typecheck`.

## Supplying data (the public copy ships none)

The `data` and `catalog` cells need two things you supply, under `data_dir` (default `data/`, git-ignored):

- `data/bl4-serial-matches.json` : a JSON **list** of rows. Fields read: `partString` (the `@U...` serial),
  `itemName`, `type`, `weaponType`, `manufacturer`, `manufacturerWeaponType`, `rarity`, `bulletType`, `source`.
  See `modules/catalog/_db.py` for exactly how each is used.
- `data/manifest/` : the game's part tables, as `category_names.tsv`, `item_names.tsv`,
  `parts/<slug>-<category_id>.tsv`, `part_meta.json`, `drops.json`, and an optional one-line `VERSION`.
  See `modules/data/CONTRACT.md` and `modules/data/__init__.py` for the formats.

**There is no generator for either in this repository.** The maintainer's copies came from an earlier,
unshipped extraction pipeline and a community-scraped list. The upstream `monokrome/bl4` toolkit has a parts
database and extraction tools that may produce comparable data, but whether its output matches these formats
is UNVERIFIED. Without them, serial decode/encode/relevel and all save editing still work; searching,
naming, rarity and drop odds do not, and the commands say so.

Never commit what you generate: game data is Gearbox / 2K material.

## The loot-pak builder and its external-tool requirement

`lootpak-plan` / `lootpak-build` turn one TOML config into a PS5 loot pak by retargeting values of existing
leaves in the game's `table_enemydrops`, `Rarity_Balance`, difficulty, lootable-balance and spawn-balance data
tables. It does this with **external programs that you must supply**, set in `config.toml [lootpak]`:

| Key | What it is |
|---|---|
| `ncstool` | a helper (not published here) built on the upstream `bl4-ncs` parser: lists leaves, sets bits, wraps, makes a pak |
| `bl4` | the upstream `monokrome/bl4` command line tool (`bl4 ncs show` decodes a data file) |
| `uextract` | the upstream pak/IoStore extractor (UNVERIFIED which crate in that workspace builds it) |
| `modwork` | the folder relative paths in a loot-pak config resolve against |

Without `ncstool` the builder cannot run: `ncstool` is not included, and this project does not tell you
how to obtain game files. The pure parts of the cell (config parsing, leaf locating logic, the decode-diff
gate, write protection) are tested against an in-memory fake tool set (`tests/lootpak_helpers.py`), so the
suite passes without any of this. Golden-build tests skip when the tools are absent.

How it stays safe: it writes only into a brand-new output folder; the plan is printed before anything is written;
the built pak is extracted and decoded again and must differ from its base by exactly the planned lines, or
the pak is renamed `.REJECTED` and no manifest is written. The subprocess adapter (`_tools.py`) is the only
code that starts a program, with an argument list and no shell. **The paths come from your `config.toml`:
anyone who can edit that file can make `lootpak-build` run a program of their choice. Treat it like a script.**

Examples live in `examples/lootpak/` (paths are relative to `modwork`). Read
`src/bl4forge/modules/lootpak/CONTRACT.md` for the scope, the sentinel-probe method and what is unverified. In
game results of these builds are mixed; see `docs/runbooks/RESEARCHER.md`.

## Web UI build

`cd ui && npm install --include=dev && npm run build` writes the bundle into `src/bl4forge/web/static/`
(git-ignored). No bundle is committed, because minified output cannot be reviewed; `serve` works without it
(JSON API only) and prints a note. See `ui/README.md` and `docs/WEB_API.md`.

## Reusing parts in another project

- **Codec** (`modules/codec/_wire.py` and `__init__.py`): pure standard library, no globals. Use through the
  `CodecPort` (`decode`, `encode`, `get_level`, `relevel`) or import `_wire` directly. The module is a port of
  Nicnl/borderlands4-serials (AGPL-3.0).
- **Save container** (`modules/save/_aes.py`, `_container.py`, `_yamltext.py`): AES-256-ECB, the zlib + length
  framing for PS5 and PC, and the text-preserving line editor. You supply the key. `_container.decrypt(data,
  key, platform)` / `encrypt(yaml_bytes, key, platform)` are the two entry points.
- **Copy-only writer** (`SaveModule.write_copy`): refuses the source path, hashes before and after, writes a sidecar.

### License obligations when you reuse or redistribute

The tree is **AGPL-3.0-only** (see `LICENSING.md`, `NOTICE`):

- Keep `LICENSE` and `NOTICE` and the credit to Nicnl/borderlands4-serials. Mark your changes.
- If you distribute it, or let others use a modified version over a network, you must make the complete
  corresponding source available under the AGPL-3.0.
- Code derived from here must be AGPL-3.0 too. If you need a different license, do not copy the codec: write it
  from the public format description instead (the upstream BSD-2-Clause toolkit is a possible reference, but
  check how its codec relates to Nicnl's first; that relationship is UNVERIFIED).
- Do not redistribute game data, saves, keys or paks with it.
