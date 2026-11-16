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
| Fonts | self-hosted with @fontsource (latin subsets only, all SIL OFL 1.1): Saira Stencil One 400 (headings), Barlow Condensed 600/700 (labels), Barlow 400/500/600, JetBrains Mono 400/500 |
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
npm run screens      # real screenshots of the mock build (see Screenshots)
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

"Break Free": a hacktivist graphic novel. Near-black ink panels with faint scanlines, cream text,
vault-yellow primary, AI-cyan secondary, hot-pink glitch accents, stencil headings, halftone dots,
hand-inked (brush) borders, a blank cracked-visor mask as the logo. Original artwork only (no
Borderlands/Gearbox, Watch Dogs/DedSec or any real group's logo, mask or fonts). All tokens live in
`src/index.css` (`@theme static`) and are used as Tailwind utilities (`bg-surface-2`,
`text-rarity-legendary`, `border-el-cryo`, ...). The token NAMES from the first design were kept so
components inherit the look: `hazard` is now vault yellow, `violet` is now AI cyan, `danger` is pink.

| Group | Tokens |
|---|---|
| Surfaces | `bg #07080b`, `surface-1 #0f1116`, `surface-2 #171a22`, `surface-3 #1e222c`, `surface-4 #272c38`, `line #3a3f4c`, `line-strong #6b7080` |
| Text | `fg #efe5c8` (cream), `fg-muted #b9b5a6`, `fg-dim #9b9889`, `serial #9fe7c0` |
| Brand | `hazard #ffe03d` (+ `hazard-hi #fff07a`, `hazard-ink #15110a`), `violet #35e8d4` (+ `violet-hi #8ff5ea`), `pink #ff3d8b` (decoration only: offset shadows, glitch) |
| Status | `ok #6ee7a0`, `warn #ffb627`, `danger #ff5a9d`, `blocked #9aa6b8` |
| Rarity | `common #d3d6dc`, `uncommon #6ee7a0`, `rare #5eb0ff`, `epic #c993ff`, `legendary #ffb627`, `pearl #c9f8ff` (+ shimmer), `vile #ff6fa8` |
| Element | `cryo #5ce1ff`, `fire #ff8a6b`, `radiation #5bff7a`, `shock #9db0ff` (+ `shock-spark #ffe14d`), `corrosive #c8f53a`, `impact #a7b1be` |

Contrast (WCAG AA, computed from relative luminance; text needs 4.5:1). Lowest of each text colour
over the five surfaces (worst case is `surface-4`, used only for hover fills): `fg` 11.1, `fg-muted`
6.8, `fg-dim` 4.8, `hazard` 10.6, `violet` 9.1, `danger` 4.8, `ok` 9.1, `warn` 8.0, `blocked` 5.7;
rarity text 4.8 to 12.2 (`rare` 6.1, `epic` 6.1, `vile` 5.4); element text 6.1 to 11.0. On
`surface-1`: `fg` 15.0, `fg-dim` 6.5, `danger` 6.5. Ink on fills: hazard 14.3, cyan 11.1, pink 5.9.
Non-text: focus ring cyan on `surface-1` 12.3 (3:1 needed), control border `line-strong` 3.8.
Colour is never the only signal: badges carry text and icons, active chips get a dot, health
state is icon plus word, diffs use del/ins.

Utilities (see `src/index.css`): `panel` (ink outline, scanlines, hard shadow), `ink-edge`
(brush-ink border via an SVG displacement filter on a pseudo-element; `html.ink-lite` drops the
filter. `src/lib/ink.ts` sets it when a 20-frame probe averages above 28 ms, or with `?ink=lite`;
`?ink=full` forces it off), `title-display` (stencil), `slashes` (`// ` prefix), `rgb-split` (static
pink/cyan text split, used on errors), `glitch` (split on hover/focus; the jitter animation only
runs under `prefers-reduced-motion: no-preference`).

## Item icons

`<ItemIcon kind rarity element maker />` (`src/components/item/ItemIcon.tsx`) draws one original
ink-style SVG silhouette per item type (pistol, SMG, shotgun, assault rifle, sniper, heavy weapon,
shield, grenade/ordnance, class mod, repair kit, enhancement, plus a generic crate). The body takes
`currentColor` from the rarity token; a small element glyph (fire, shock, cryo, corrosive, radiation,
impact) and a generic maker mark (a shape picked from the maker name, never a real logo) sit in the
corners (`marks={false}` for tiny icons). `iconKindOf` (`src/lib/itemKind.ts`, unit-tested) maps what
the API returns (`weapon_type`, `type`, decoded `category`); anything unknown becomes the crate.
Used on result cards, tray rows and the workbench dossier. `scripts/icons-sheet.tsx` renders a sheet.

## Art

`public/art/takeover.webp` and `ai-ally.webp` (cropped, about 120 KB each, from
`docs/images/art/v4`) illustrate empty and error states (`components/item/states.tsx`).

## Screenshots

`npm run build:mock`, serve it (`npx vite preview --mode mock --outDir dist-mock --port 4173`), then
`BL4_CHROMIUM=<chrome.exe> npm run screens -- http://127.0.0.1:4173 ../docs/images/screens` takes
1440x900 @2x shots of every screen, checks the keyboard focus ring and that the glitch animation
is off under `prefers-reduced-motion`. Mock mode fills an empty fixture set with the invented
catalog in `src/mock/demo.ts` (fictional makers and items; its serials decode nowhere).

## Motion (Motion Primitives / Watermelon-style, rebuilt with `motion`)

Text scramble (wordmark, item names, dossier title), staggered AnimatedGroup entry for result
cards, spotlight + border-glow cards that follow the pointer (CSS variables, no re-render),
magnetic primary buttons, number tickers (catalog count, result count, tray badge, health score),
shared-layout tab and nav indicators, copy-button morph with a ring pulse, drag-reorder in the tray,
flowing dashed edges in the health mesh. `prefers-reduced-motion` turns all of it into instant
state changes (MotionConfig `reducedMotion="user"` plus a CSS kill switch; scramble and tickers
render final values).

## Accessibility

Real buttons, labels and fieldsets; visible 3 px cyan focus ring; skip-to-content; one `h1` per
screen; tabs with arrow keys; modal dialogs trap focus and close on Esc; results, health and
toasts announce through `aria-live`; the mesh nodes are focusable buttons with full labels.
The earlier axe-core pass predates the redesign and has not been re-run.
