/**
 * Dev helper: renders every ItemIcon (all rarities x kinds) to a standalone HTML sheet using the
 * built stylesheet.   vite-node scripts/icons-sheet.tsx <built.css> <out.html>
 */
import { writeFileSync } from 'node:fs'
import { renderToStaticMarkup } from 'react-dom/server'
import { ItemIcon } from '../src/components/item/ItemIcon'
import { ICON_KINDS, ICON_LABEL } from '../src/lib/itemKind'

const cssPath = process.argv[2] ?? ''
const out = process.argv[3] ?? 'icons.html'
const link = cssPath ? `<link rel="stylesheet" href="/assets/${cssPath.split(/[\/]/).pop()}">` : ''
const rarities = ['Legendary', 'Epic', 'Rare', 'Uncommon', 'Common', 'Pearl']
const els = ['fire', 'shock', 'cryo', 'corrosive', 'radiation', 'impact', null] as const
const makers = ['Breakfree Arms', 'Ajar Industries', 'Lockpick & Sons']
const cells = ICON_KINDS.map((k, i) =>
  renderToStaticMarkup(
    <figure style={{ margin: 0 }}>
      <div style={{ background: '#0f1116', border: '2px solid #3a3f4c', padding: 14 }}>
        <ItemIcon kind={k} rarity={rarities[i % rarities.length]} element={els[i % els.length]} maker={makers[i % makers.length]} />
      </div>
      <figcaption style={{ color: '#b9b5a6', font: '13px Barlow, sans-serif', marginTop: 6 }}>
        {ICON_LABEL[k]} / {rarities[i % rarities.length]}
      </figcaption>
    </figure>,
  ),
)
const html = `<!doctype html><html><head><meta charset="utf-8"><title>Item icons</title>${link}<style>body{padding:24px;background:#07080b}.sheet{display:grid;grid-template-columns:repeat(4,240px);gap:22px}</style></head><body><div class="sheet">${cells.join('')}</div></body></html>`
writeFileSync(out, html)
