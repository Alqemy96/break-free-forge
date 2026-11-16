# bl4-forge UI

The local web interface for bl4-forge: a single-page app served by `bl4forge serve` from
`src/bl4forge/web/static/`, talking only to the same-origin JSON API under `/api`
(contract: `docs/WEB_API.md`). Local-first, one user, dark theme only.

## Stack (decided)

| Layer | Choice |
|---|---|
| Build | Vite 7 (`base: '/'`, hashed assets in `assets/`) |
| UI | React 19 + TypeScript 5.9 (`strict`, `noUncheckedIndexedAccess`, no `any`) |
| Styling | Tailwind CSS v4 (CSS-first `@theme static` tokens in `src/index.css`) |
| Components | shadcn/ui-style primitives written in-repo (`src/components/ui`, cva + tailwind-merge; `components.json` is there for `npx shadcn add` later) |
| Motion | `motion` 12 (`motion/react`), wrapped in `MotionConfig reducedMotion="user"` |
| Icons / state | lucide-react, zustand (tiny stores around pure, unit-tested reducers) |
| Fonts | self-hosted with @fontsource (latin subsets only): Barlow Condensed 600/700, Barlow 400/500/600, JetBrains Mono 400/500 |
| Tests | Vitest (pure logic only: client error mapping, reducers, formatters, hash routing, spec parsing, mesh layout) |

No CDN, no analytics, no network calls except `/api` (and the Vite dev server in development).

## Commands

Run from `ui/`. Some Windows shells set `NODE_ENV=production` globally, which makes npm skip dev
dependencies, so always install with `--include=dev`:

```bash
npm install --include=dev
npm run dev          # Vite on http://127.0.0.1:5173, proxies /api -> http://127.0.0.1:8734 (run `bl4forge serve` too)
npm run dev:mock     # same UI on in-memory fixtures, no server needed
npm run typecheck    # tsc --noEmit (src + scripts)
npm test             # vitest run
npm run build        # typecheck, then build into ../src/bl4forge/web/static/
npm run smoke        # contract smoke test against a RUNNING server (BL4FORGE_URL to override)
npm run fixtures     # recapture mock fixtures from the engine (needs python3; run from ui/)
```

`npm run build` empties `src/bl4forge/web/static/` first (`emptyOutDir`). Where deleting files is
not allowed, set `BL4FORGE_UI_NO_EMPTY=1` (old hashed assets then stay behind; delete them by hand).
After a build, `bl4forge serve` serves the new UI; `index.html` is no-cache and the hashed assets
are immutable, so a reload always picks up the latest build.

## Mock mode

`VITE_MOCK=1` (or `--mode mock`, which reads `.env.mock`) swaps the HTTP client for
`src/mock/mockApi.ts`: the same `Api` interface, answering from `src/mock/fixtures.json`. The
fixtures are real output of the web layer's own handlers (`bl4forge.web._api.Api`), captured by
`scripts/capture_fixtures.py`, so shapes match the server exactly. The mock is a compile-time
branch (`__BL4_MOCK__`), so the production bundle contains none of it.

Mock-only scenarios, added to the page URL before the hash:

- `?scenario=sick` catalog failed, builder blocked: search/build return 503 `module_unavailable`
- `?scenario=degraded` ops degraded: everything answers, the degraded banner shows
- `?scenario=down` no server: the unreachable banner shows

The mock only decodes the ~60 serials it captured; any other pasted serial gets a `serial_error`.

## Screens

- **Forge** (`#/forge?...`): search panel (name, type/element/rarity chips, manufacturer, vault
  hunter, level, limit, include-unowned and verify-element toggles) and an animated result grid.
  Hidden content packs, element-verification drops, server notes and the limit cap are always
  reported above the results. The search lives in the URL hash, so reload/back restore it.
- **Loadout tray** (right dock at >= 1280 px, overlay drawer below): groups (Weapons/Gear by default;
  add, rename, merge, reorder, remove empty), drag or arrow reordering, inline display name, note
  and group per item, sheet title and level, Build sheet (explicit-serial `/api/build`), Copy all
  codes, Clear (two-step). Persisted in `localStorage` (`bl4forge.tray.v1`, failures ignored).
  *Quick build* tab: paste the cli's JSON spec, build with server-side search, see unmatched and
  warnings, open the sheet, or add every resolved code to the tray.
- **Sheet viewer**: the server's HTML sheet in `<iframe srcdoc sandbox="allow-scripts">` (no
  `allow-same-origin`, so the sheet's copy buttons work but it cannot touch the app), plus Download
  HTML, Download text and Copy all codes.
- **Workbench** (`#/workbench?serial=...`): identify any serial (optionally at a level): name,
  rarity/element/level/category/content-pack badges, drop odds (always "base rates"), structural
  problems ("passed structural checks", never "valid in game"), numbered parts (position = swap
  number; unknown parts and category links highlighted). Re-level, set element (weapons only;
  Impact strips it), reseed (optional seed), swap parts (load a source serial, pick positions,
  cross-category needs an explicit danger toggle). Every change is a proposal with a character
  diff of the serial and the field diff from `/api/diff`; *Use this* pushes it on a history stack,
  *Undo* steps back.
- **Health** (`#/health`): the seven modules as a hex-cell mesh (edges = `requires`, long edges arc
  around cells, state colours, hover/focus lights up neighbours, Enter pins), a detail panel with
  checks, a table, Refresh and 15 s auto-refresh. The header dot turns amber/red with a tooltip,
  and any 503 shows a banner naming the module.

Keyboard: `/` focus search (or the serial box), `Ctrl+Enter` run (search / identify / refresh;
build when focus is in the tray), `Esc` closes the top overlay, `L` toggles the tray, `1` `2` `3`
switch screens, `?` lists shortcuts.

## Code map

```
src/api/types.ts        the contract as TypeScript (single source of truth)
src/api/client.ts       typed fetch client; every failure -> ApiError {code, message, status, module}
src/api/index.ts        real client, or the mock in mock mode
src/state/              tray + workbench reducers (pure, tested), app/toast/tray stores
src/features/forge      search form <-> params <-> hash, store, panel, results, item card
src/features/loadout    tray, quick build, build store, sheet viewer
src/features/workbench  dossier, parts table, actions, proposal + diff, history
src/features/health     mesh layout (pure, tested), mesh diagram, screen
src/components/ui       button, input, label/field, badge, chip, switch, tabs, tooltip, select, number field
src/components/fx       text scramble, animated group, spotlight, magnetic, number ticker, copy button
src/components/layout   header, nav rail, banners, toaster, shortcuts
src/mock/               mock Api, fixtures, stand-in sheet
scripts/                capture_fixtures.py, smoke.ts
```

## Design tokens

Industrial loot-locker: graphite/gunmetal plates with a faint brushed sheen and film grain,
hazard-orange primary, deep violet secondary, mono uppercase telemetry labels, chamfered item
plates. All tokens live in `src/index.css` (`@theme static`) and are used as Tailwind utilities
(`bg-surface-2`, `text-rarity-legendary`, `border-el-cryo`, ...).

| Group | Tokens |
|---|---|
| Surfaces | `bg #0b0c0e`, `surface-1 #111317`, `surface-2 #171a1f`, `surface-3 #1e2228`, `surface-4 #272c34`, `line #2b3038`, `line-strong #3d4450` |
| Text | `fg #ece9e3`, `fg-muted #a9aeb6`, `fg-dim #878d96`, `serial #9fe7c0` |
| Brand | `hazard #ff6a13` (+ `hazard-hi #ff8c42`, `hazard-ink #190a00` for text on orange), `violet #7c4dff`, `violet-hi #bba6ff`, `violet-deep #24164f` |
| Status | `ok #4ade80`, `warn #fbbf24`, `danger #ff5468`, `blocked #9aa6b8` |
| Rarity | `common #cfd3d9`, `uncommon #4ade80`, `rare #3d9bff`, `epic #b46bff`, `legendary #ffb627`, `pearl #c9f8ff` (+ shimmer), `vile #ff3d7f` |
| Element | `cryo #5ce1ff`, `fire #ff5a36`, `radiation #5bff7a`, `shock #7891ff` (+ `shock-spark #ffe14d` bolt), `corrosive #c8f53a`, `impact #a7b1be` |

Contrast (WCAG AA, measured on `surface-1`): `fg-dim` 5.4:1, `hazard` 6.5:1, `hazard-ink` on
`hazard` 6.8:1, `rare` 6.5:1, `epic` 5.9:1, `vile` 5.6:1, `fire` 6.1:1, `shock` 6.2:1. `violet` is
used for fills/borders only; violet text uses `violet-hi`. Colour is never the only signal: rarity
and element badges carry text and icons, active chips get a dot and weight, diffs use del/ins.

## Motion (Motion Primitives / Watermelon-style, rebuilt with `motion`)

Text scramble (wordmark, item names, dossier title), staggered AnimatedGroup entry for result
cards, spotlight + border-glow cards that follow the pointer (CSS variables, no re-render),
magnetic primary buttons, number tickers (catalog count, result count, tray badge, health score),
shared-layout tab and nav indicators, copy-button morph with a ring pulse, drag-reorder in the tray,
flowing dashed edges in the health mesh. `prefers-reduced-motion` turns all of it into instant
state changes (MotionConfig `reducedMotion="user"` plus a CSS kill switch; scramble and tickers
render final values).

## Accessibility

Real buttons, labels and fieldsets; visible 2 px hazard focus ring; skip-to-content; one `h1` per
screen; tabs with arrow keys; modal dialogs trap focus and close on Esc; results, health and
toasts announce through `aria-live`; the mesh nodes are focusable buttons with full labels.
Checked with axe-core on the mock build: no violations.
