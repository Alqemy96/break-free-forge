/**
 * Real screenshots of the mock-mode app (docs/images/screens/*.png at 1440x900 @2x) plus two
 * accessibility probes (keyboard focus ring, prefers-reduced-motion).
 *
 *   npm run build:mock && npx vite preview --mode mock --outDir dist-mock --port 4173 &
 *   BL4_CHROMIUM=<path to chrome.exe> node scripts/screens.mjs http://127.0.0.1:4173 ../docs/images/screens
 *
 * Needs playwright-core (devDependency) and any Chromium (BL4_CHROMIUM, or Playwright's own cache).
 */
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright-core'

const base = process.argv[2] ?? 'http://127.0.0.1:4173'
const out = process.argv[3] ?? '../docs/images/screens'
mkdirSync(out, { recursive: true })

const SERIAL = '@UDEMO-crowbar-L60-0001-notarealserial'
const browser = await chromium.launch({ executablePath: process.env.BL4_CHROMIUM || undefined })
const report = {}

async function open(path, { reducedMotion = 'no-preference' } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, reducedMotion })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text())
  })
  await page.goto(base + path)
  await page.evaluate(() => document.fonts.ready)
  return { ctx, page, errors }
}

async function shot(name, path, prep) {
  const { ctx, page, errors } = await open(path)
  if (prep) await prep(page)
  await page.waitForTimeout(1500) // mock latency + entry animations
  await page.screenshot({ path: `${out}/${name}.png` })
  report[name] = { errors }
  await ctx.close()
}

await shot('forge', '/#/forge?q=o&level=60&limit=30')
await shot('forge-empty', '/#/forge')
await shot('workbench', `/#/workbench?serial=${encodeURIComponent(SERIAL)}`)
await shot('workbench-empty', '/#/workbench')
await shot('health', '/#/health')
await shot('health-degraded', '/?scenario=degraded#/health')
await shot('forge-error', '/?scenario=sick#/forge?q=o&level=60&limit=30')
await shot('tray', '/#/forge?q=o&level=60&limit=30', async (page) => {
  await page.waitForSelector('article')
  const adds = page.getByRole('button', { name: /^Loadout$/ })
  const n = Math.min(3, await adds.count())
  for (let i = 0; i < n; i++) await adds.nth(0).click()
  await page.keyboard.press('l')
})

// keyboard focus: tab to the first card's inspect button and measure the focus outline
{
  const { ctx, page } = await open('/#/forge?q=o&level=60&limit=30')
  await page.waitForSelector('article')
  await page.keyboard.press('Tab') // switch to keyboard modality so :focus-visible applies
  await page.locator('article').first().getByRole('button', { name: /Inspect/ }).focus()
  const focus = await page.evaluate(() => {
    const el = document.activeElement
    if (!el || el === document.body) return null
    const cs = getComputedStyle(el)
    return { tag: el.tagName, text: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 40), outlineStyle: cs.outlineStyle, outlineWidth: cs.outlineWidth, outlineColor: cs.outlineColor }
  })
  report.focus = focus
  await page.screenshot({ path: `${out}/forge-focus.png` })
  await ctx.close()
}

// reduced motion: the hover glitch must not animate, and must animate when motion is allowed
for (const rm of ['no-preference', 'reduce']) {
  const { ctx, page } = await open('/#/forge?q=o&level=60&limit=30', { reducedMotion: rm })
  await page.waitForSelector('article')
  const btn = page.getByRole('button', { name: /Loadout/ }).first()
  await btn.hover()
  await page.waitForTimeout(100)
  report[`hover-${rm}`] = await btn.evaluate((el) => {
    const cs = getComputedStyle(el)
    return { animationName: cs.animationName, textShadow: cs.textShadow !== 'none' }
  })
  await ctx.close()
}

console.log(JSON.stringify(report, null, 2))
await browser.close()
