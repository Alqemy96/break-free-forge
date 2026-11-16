# bl4-forge architecture: a mesh of cells

Every capability is a **cell** (module). A cell knows its own purpose, declares which neighbours it
needs, and implements exactly one **port** (interface). The framework (`core/`) is the membrane:
shared types, shared vocabulary, ports, registry, config, and the doctor. No logic lives in it.

```
codec      bits <-> blocks            (pure, no neighbours)
data       the game's manifest tables (read-only lookups)
render     Loadout -> HTML / text     (pure formatting)
save       PS5/PC .sav <-> YAML, line-level text patches, copy-only writes (leaf; keys from config [save])
rules      ownership + structural validation           <- codec, data
ops        identify / element / seed / swap / diff     <- codec, data, rules
catalog    searchable community serial database        <- codec, data, rules, ops
builder    requests -> verified Loadout                <- catalog, ops
cli        the command line (outer layer, uses Forge)
web        local UI (outer layer, phase 3)
```

## Why this shape
- **Contained failure.** `Forge.build()` starts cells in dependency order. A cell that fails to
  start is `FAILED`; cells that need it are `BLOCKED`; everything else keeps working. The doctor
  names the sick cell and why.
- **Separable repair.** Each module has its own directory, tests, and `CONTRACT.md`. Fixing one never
  requires editing another, because they only meet at ports.
- **Cells see only their declared neighbours.** `ModuleContext.dep()` refuses anything not in
  `requires`. Hidden coupling raises `UndeclaredDependency` instead of rotting silently.
- **Swappable.** `Forge.build(overrides={"data": FakeData})` replaces any cell, for tests or for a
  future second implementation.
- **One vocabulary.** Elements, rarities, characters are defined once in `core/vocab.py`. The legacy
  forge kept two element tables with different conventions; that class of bug is designed out.

## Hard-won rules (carried over from the legacy forge; each is enforced by a test)
- Trust the decoded serial, never a database label (labels are wrong on ~3.3% of weapons).
- Rarity comes from `part_meta.json`, never parsed from a part name (14/20 pearls are named `comp_05_legendary_*`).
- Pearlescents legitimately carry two composition parts; the highest tier governs.
- Ownership is judged per part, and filtered results are reported, never silently truncated.
- `swap` refuses cross-category swaps; finer part-compatibility is NOT enforced (say "passed
  structural checks", never "valid in game").
- A failed re-level is a warning, never silently the original level.
- Drop odds are base rates; luck and event modifiers are not in the data.

## Build order
Phase 0 framework (done first) -> wave 1 codec/data/render -> wave 2 rules/ops/catalog ->
wave 3 builder/cli -> integration + parity + doctor -> local web UI.
