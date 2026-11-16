# CONTRACT - module `render`

**Purpose:** Present a Loadout as a self-contained HTML code sheet and a plain-text list.
**Requires:** nothing (a leaf cell)
**Class:** `RenderModule` in `src/bl4forge/modules/render/__init__.py` (export it as `MODULE`; split into more files inside this directory as you like)
**Read first:** `docs/AGENT_RULES.md` (module rules; see also docs/runbooks/DEVELOPER.md), `docs/ARCHITECTURE.md`, the `RenderPort` docstring in `core/ports.py`.
**Tests live in:** `tests/modules/test_render*.py`

## Port to implement
`RenderPort` in `core/ports.py`.

## Port from legacy
`legacy/skills/bl4-loadout/scripts/forge.py`: `CSS`, `COPY_JS`, `_card`, `render_html`, `plain_text`, `_elem_key`, `ELEM_LABEL`,
`ELEM_CLASS`. Input is `core.types.Loadout` / `LoadoutItem` (element is a vocab name or None; map it
to the CSS class here, using `core.vocab.ELEMENT_LABELS`). Keep the look (this is the sheet the maintainer uses);
the web UI phase will restyle later, so keep CSS in one constant.
Import instructions text (save-editor.be Item Builder: paste serial -> Decode & Validate -> Add to
Backpack -> nothing touches the save until Overwrite Existing Save) must stay in the sheet.

## Invariants
- `escapes_everything`: a name/note/label containing `<script>` or `"` is escaped; only `<em>`/`</em>` survive in notes.
- `self_contained`: no external URLs, no `<link>`, no remote script.
- `every_serial_present`: each item's serial appears in html() and exactly once per line in text().
- `text_is_pasteable`: text() is one serial per line under group headings; no HTML.
- `write_creates_both_files`: write() returns (html_path, text_path) and both exist; default text path is html path with .txt.
- `legacy_content_parity`: render the same items with legacy `render_html`/`plain_text` and compare the
  set of visible strings (names, levels, serials); layout/whitespace may differ.

## Health
Render a one-item Loadout built in code; assert the serial appears and nothing raises.

## Deviations from legacy
Verified by `tests/modules/test_render.py`: for the same items the card markup, page chrome (title,
import instructions, checklist, footer) and plain text are identical to legacy `render_html` /
`plain_text` over the whole serial database (9,875 rows) and over 30 enriched real entries. The
differences below are the only ones, and each is intentional.

Input / mapping
- Elements arrive as vocab names (`shock`, `radiation`, ...). The legacy `ELEM_LABEL`/`ELEM_CLASS`
  keyed by `electric`/`N/A` are gone; labels come from `core.vocab.ELEMENT_LABELS`. The CSS class
  map (`radiation`->`rad`, `corrosive`->`corr`) lives in `style.ELEMENT_CSS_CLASS`. `None`, `""`
  and `"N/A"` show no badge. An unknown element string is shown (escaped) with class `none`,
  never hidden.
- Legacy `true_rarity or rarity`, `category or label`, `display_name or legendary_name or name`
  now arrive pre-resolved on `LoadoutItem` (`rarity` is already the best truth); the sub line is
  still `category-or-label · rarity · Lv N`.

Legacy bugs not preserved
- `note` was inserted RAW (any HTML ran). Now escaped; only `<em>`/`</em>` (case-insensitive,
  emitted lower-case, no attributes) pass, and they are always balanced: an unclosed `<em>` is
  closed at the end of the note, a stray `</em>` stays visible as text.
- HTML silently DROPPED any item whose group was missing from `groups` (and every ungrouped item
  when any group was listed), while the text kept it. Now no item is ever dropped: groups render
  in `Loadout.groups` order, then groups named only on an item (first appearance), then ungrouped
  items under `Loadout` (no groups at all, as before) or `Other` (some items are grouped).
  Groups with no items are skipped, as before.
- Text used to print a `[group]` heading every time the group changed in ITEM order (a repeated,
  non-contiguous group printed its heading twice; ungrouped items fell under the previous group's
  heading). `text()` now uses exactly the same sections as `html()`: one heading per group, an
  `Other` heading for ungrouped items in a grouped loadout. For contiguous groups (what the builder
  produces) the output is byte-identical to legacy.
- Plain text is single-line safe: newlines/tabs/control characters in names, titles and group names
  collapse to single spaces, and whitespace/control characters are removed from serials, so a data
  field can never fabricate an extra line (or a fake serial line).
- `1 import-ready codes` / `1 parts` pluralised correctly (`1 import-ready code`, `1 part`).

Additions (new content; legacy never showed these)
- Item `warnings` render as `<p class="warn"><b>Warning</b> · ...</p>` inside the card
  (e.g. "database says element Fire, the serial says Impact"). `Loadout.unmatched` and
  `Loadout.warnings` render as "Not matched" / "Warnings" sections before the checklist, only when
  non-empty. They are NOT in `text()` (the text is a paste-safe list of serials).
- An empty loadout renders a page saying "No items in this loadout." instead of an empty section.
- Three additive CSS rules (`.warn`, `.warn b`, `.empty`) appended to the one `CSS` constant; the
  legacy rules are untouched.

I/O
- `write()` creates parent directories, writes UTF-8 with `\n` newlines on every platform (legacy
  used the platform default), and returns `(html_path, text_path)` exactly as given
  (`os.fspath`), with the default text path `splitext(html_path)[0] + ".txt"`.
- `write()` raises `ForgeError` (never a bare `OSError`) if a file cannot be written, and also if
  the html and text paths would be the same file (e.g. `html_path="x.txt"` with no `text_path`),
  which would otherwise overwrite the sheet with the list. Both documents are rendered before the
  disk is touched.

Calling convention for neighbours
- `forge.render.html(loadout)`, `.text(loadout)`, `.write(loadout, html_path, text_path=None)`.
  `Loadout.groups` should be the ordered group names (as the legacy `groups` list); `Loadout.level`
  feeds the subtitle ("re-leveled to N") and the text's `All codes re-leveled to N.` line.
  `LoadoutItem.note` is plain text (use `<em>...</em>` for emphasis, nothing else is honoured).

