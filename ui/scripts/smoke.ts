/**
 * Contract smoke test against a RUNNING `bl4forge serve` (not part of `npm test`).
 *   npm run smoke                      # http://127.0.0.1:8734
 *   BL4FORGE_URL=http://127.0.0.1:9000 npm run smoke
 * Calls every endpoint through the UI's own client and checks the fields the UI reads.
 */
import { ApiError, createHttpApi } from '../src/api/client'

const base = `${(process.env.BL4FORGE_URL ?? 'http://127.0.0.1:8734').replace(/\/$/, '')}/api`
const api = createHttpApi((input, init) => fetch(input, init), base)
let failures = 0

function check(label: string, obj: unknown, keys: string[]): void {
  const missing = keys.filter((k) => !obj || typeof obj !== 'object' || !(k in obj))
  if (missing.length) {
    failures++
    console.log(`FAIL ${label}: missing ${missing.join(', ')}`)
  } else console.log(`ok   ${label}`)
}

async function expectError(label: string, run: () => Promise<unknown>, code: string): Promise<void> {
  try {
    await run()
    failures++
    console.log(`FAIL ${label}: expected ${code}, got success`)
  } catch (err) {
    const ok = err instanceof ApiError && err.code === code
    if (!ok) failures++
    console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}: ${err instanceof ApiError ? `${err.code} (${err.status}) ${err.message}` : String(err)}`)
  }
}

async function main(): Promise<void> {
  const meta = await api.meta()
  check('meta', meta, ['version', 'level', 'character', 'owned_packs', 'catalog_count', 'manifest_version', 'elements', 'rarities', 'characters', 'types'])
  const health = await api.health()
  check('health', health, ['ok', 'modules'])
  check('health.modules[0]', health.modules[0], ['name', 'state', 'detail', 'purpose', 'requires', 'contract_problems', 'checks'])
  check('stats', await api.stats(), [])

  const search = await api.search({ query: 'anarchy', element: 'cryo', limit: 3, level: meta.level })
  check('search', search, ['count', 'level', 'results', 'hidden', 'dropped_element_mismatch'])
  const row = search.results[0]
  check('search.results[0]', row, ['serial', 'name', 'type', 'weapon_type', 'manufacturer', 'label', 'rarity', 'element', 'source', 'level', 'decoded'])
  check('search.results[0].decoded', row?.decoded, ['display_name', 'category', 'rarity', 'element', 'owned', 'warnings'])
  const cm = await api.search({ type: 'classmod', limit: 2 })
  console.log(`     classmod search notes: ${JSON.stringify(cm.notes ?? null)}`)
  if (!row) throw new Error('no search result to continue with')

  const id = await api.identify({ serial: row.serial })
  check('identify', id, ['serial', 'info', 'odds', 'parts', 'problems', 'is_weapon', 'can_set_element'])
  check('identify.parts[0]', id.parts[0], ['position', 'token_index', 'label', 'category_id', 'index', 'raw', 'category_link'])
  const rel = await api.transform({ serial: row.serial, op: 'relevel', level: 50 })
  check('transform relevel', rel, ['serial', 'previous', 'note', 'info', 'parts'])
  const el = await api.transform({ serial: row.serial, op: 'set_element', element: 'fire' })
  check('transform set_element', el, ['serial', 'previous', 'note'])
  const seed = await api.transform({ serial: row.serial, op: 'reseed' })
  console.log(`     reseed seed field: ${String(seed.seed)}; note: ${seed.note}`)
  const diff = await api.diff(row.serial, el.serial)
  check('diff', diff, ['rows'])
  console.log(`     diff rows: ${JSON.stringify(diff.rows)}`)

  const build = await api.build({
    title: 'Smoke',
    level: meta.level,
    requests: [{ group: 'Weapons', serial: row.serial, name: row.name, label: row.label }, { group: 'Gear', type: 'repkit' }],
  })
  check('build', build, ['loadout', 'html', 'text'])
  check('build.loadout', build.loadout, ['title', 'level', 'groups', 'unmatched', 'warnings', 'items'])
  check('build.loadout.items[0]', build.loadout.items[0], ['name', 'serial', 'shown_name', 'group', 'rarity', 'element', 'odds', 'warnings'])
  console.log(`     build: ${build.loadout.items.length} items, shown names ${JSON.stringify(build.loadout.items.map((i) => i.shown_name))}, html ${build.html.length} chars`)

  await expectError('identify garbage -> serial_error', () => api.identify({ serial: '@Unot-a-serial' }), 'serial_error')
  await expectError('set_element on gear -> bad_request', async () => {
    const gear = (await api.search({ type: 'shield', limit: 1 })).results[0]
    if (!gear) throw new Error('no shield')
    await api.transform({ serial: gear.serial, op: 'set_element', element: 'cryo' })
  }, 'bad_request')
  await expectError('empty build -> bad_request', () => api.build({ requests: [] }), 'bad_request')

  console.log(failures ? `\n${failures} check(s) failed` : '\nall contract checks passed')
  process.exitCode = failures ? 1 : 0
}

main().catch((err) => {
  console.error(err instanceof ApiError ? `${err.code} (${err.status}): ${err.message}` : err)
  process.exitCode = 1
})
