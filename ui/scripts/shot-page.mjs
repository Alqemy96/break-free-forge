/** Screenshot one URL: node scripts/shot-page.mjs <url> <out.png> [width] [height] */
import { chromium } from 'playwright-core'
const [url, out, w = '1100', h = '900'] = process.argv.slice(2)
const b = await chromium.launch({ executablePath: process.env.BL4_CHROMIUM || undefined })
const p = await b.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: 2 })
await p.goto(url)
await p.evaluate(() => document.fonts.ready)
await p.screenshot({ path: out, fullPage: true })
await b.close()
