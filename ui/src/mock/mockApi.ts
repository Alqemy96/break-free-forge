/**
 * Mock mode (VITE_MOCK=1): an in-memory Api shaped exactly like docs/WEB_API.md, backed by real
 * engine output captured with ui/scripts/capture_fixtures.py. Never part of the production bundle.
 *
 * Scenarios (add to the page URL): ?scenario=sick (catalog failed, builder blocked: 503s),
 * ?scenario=degraded (ops degraded, everything still answers), ?scenario=down (no server).
 */
import { ApiError } from '@/api/client'
import type {
  Api,
  BuildRequest,
  BuildResponse,
  DiffRow,
  ElementId,
  Health,
  IdentifyPart,
  IdentifyResponse,
  LoadoutItem,
  Meta,
  ModuleRow,
  RequestOptions,
  SearchParams,
  SearchResponse,
  SearchResultRow,
  Stats,
  TransformRequest,
  TransformResponse,
} from '@/api/types'
import raw from './fixtures.json'
import { DEMO_COUNT, demoIdentify, demoPool, demoStats } from './demo'
import { renderMockSheet, renderMockText } from './sheet'

interface Fixtures {
  meta: Meta
  health: Health
  pool: SearchResultRow[]
  identify: Record<string, IdentifyResponse>
  transforms: Record<string, TransformResponse | string>
  diff: { a: string; b: string; rows: DiffRow[] }
  build: BuildResponse
  stats: Stats
}

const fx = raw as unknown as Fixtures

// The public tree ships no captured game data, so an empty fixture set is filled with the invented
// demo catalog (./demo.ts) to keep mock mode usable. Captured fixtures, when present, win.
if (fx.pool.length === 0) {
  fx.pool = demoPool()
  fx.identify = { ...demoIdentify(), ...fx.identify }
  fx.stats = demoStats()
  fx.meta.catalog_count = DEMO_COUNT
  fx.meta.manifest_version = 'demo fixtures (fictional)'
}

type Scenario = 'sick' | 'degraded' | 'down' | null

function readScenario(): Scenario {
  try {
    const value = new URLSearchParams(window.location.search).get('scenario')
    return value === 'sick' || value === 'degraded' || value === 'down' ? value : null
  } catch {
    return null
  }
}

const TYPE_MATCH: Record<string, (r: SearchResultRow) => boolean> = {
  pistol: (r) => r.weapon_type === 'pistol',
  shotgun: (r) => r.weapon_type === 'shotgun',
  smg: (r) => r.weapon_type === 'smg',
  assault_rifle: (r) => r.weapon_type === 'assaultrifle',
  assaultrifle: (r) => r.weapon_type === 'assaultrifle',
  ar: (r) => r.weapon_type === 'assaultrifle',
  sniper: (r) => r.weapon_type === 'sniper',
  heavy: (r) => r.weapon_type === 'heavy',
  weapon: (r) => r.type === 'weapon',
  shield: (r) => r.type === 'shield',
  classmod: (r) => r.type === 'classmod',
  repkit: (r) => r.type === 'repair_kit',
  grenade: (r) => r.type === 'gadget',
  enhancement: (r) => r.type === 'enhancement',
}

const ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{/}~'

function hash(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619)
  return h >>> 0
}

/** A deterministic "new" serial: same length, a few characters changed. */
function mutate(serial: string, salt: string): string {
  const chars = [...serial]
  let h = hash(serial + salt)
  for (let k = 0; k < 4; k++) {
    const at = 6 + (h % Math.max(1, chars.length - 8))
    chars[at] = ALPHABET[(h >>> 8) % ALPHABET.length] ?? 'x'
    h = Math.imul(h ^ (h >>> 13), 2654435761) >>> 0
  }
  return chars.join('')
}

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T

const UNOWNED_PACK = { pack: 'expansion_pack_1', label: 'Expansion Pack 1 - The Locksmith Holiday (demo)' }
const ELEMENT_PART_LABEL: Record<ElementId, string> = {
  cryo: 'Cryo',
  fire: 'Fire',
  radiation: 'Radiation',
  shock: 'Shock',
  corrosive: 'Corrosive',
  impact: 'Impact',
}
const ELEMENT_LABELS = new Set(Object.values(ELEMENT_PART_LABEL))

export function createMockApi(): Api {
  const scenario = readScenario()
  const known = new Map<string, IdentifyResponse>(Object.entries(fx.identify))
  for (const t of Object.values(fx.transforms)) if (typeof t !== 'string') known.set(t.serial, stripTransform(t))

  async function wait(opts: RequestOptions | undefined, ms = 160 + Math.random() * 260): Promise<void> {
    if (scenario === 'down') {
      await new Promise((r) => setTimeout(r, 300))
      throw new ApiError('network', 'Cannot reach the forge server. Start it with `bl4forge serve` (it listens on 127.0.0.1:8734), then retry.')
    }
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, ms)
      opts?.signal?.addEventListener('abort', () => {
        clearTimeout(timer)
        reject(new ApiError('aborted', 'Request cancelled.'))
      })
    })
  }

  function unavailable(module: string): ApiError {
    const why = module === 'catalog' ? 'failed: DataMissing: serial database not found at data/serials.json' : 'blocked: needs catalog which is failed'
    return new ApiError('module_unavailable', `module '${module}' is unavailable (${why}) (run 'bl4forge doctor' for details)`, 503, module)
  }

  function lookup(serial: string): IdentifyResponse {
    const s = serial.trim()
    if (!s.startsWith('@U')) throw new ApiError('serial_error', "not a serial: it must start with '@U'", 400)
    const hit = known.get(s)
    if (!hit) {
      throw new ApiError(
        'serial_error',
        `cannot decode this serial in mock mode (the mock only knows ${known.size} captured serials; run the real server for any code)`,
        400,
      )
    }
    return hit
  }

  function remember(payload: IdentifyResponse): IdentifyResponse {
    known.set(payload.serial, payload)
    return payload
  }

  function health(): Health {
    const h = clone(fx.health)
    if (scenario === 'sick') {
      h.ok = false
      h.modules = h.modules.map((m): ModuleRow => {
        if (m.name === 'catalog') {
          return { ...m, state: 'failed', detail: 'DataMissing: serial database not found at data/serials.json', checks: m.checks.map((c, i) => (i === 0 ? { ...c, ok: false, detail: 'file not found' } : c)) }
        }
        if (m.name === 'builder') return { ...m, state: 'blocked', detail: 'needs catalog which is failed', checks: [] }
        return m
      })
    } else if (scenario === 'degraded') {
      h.ok = false
      h.modules = h.modules.map((m): ModuleRow =>
        m.name === 'ops'
          ? { ...m, state: 'degraded', detail: '6/7 known-answer checks passed', checks: m.checks.map((c, i) => (i === m.checks.length - 1 ? { ...c, ok: false, detail: 'swap round-trip differs' } : c)) }
          : m,
      )
    }
    return h
  }

  function searchRows(params: SearchParams): SearchResponse {
    const limit = Math.min(200, Math.max(1, params.limit ?? 25))
    const type = params.type?.trim().toLowerCase()
    if (type && !TYPE_MATCH[type]) throw new ApiError('bad_request', `unknown type '${params.type}'`, 400)
    const q = params.query?.trim().toLowerCase()
    const man = params.manufacturer?.trim().toLowerCase()
    const rarity = params.rarity?.trim().toLowerCase()
    const notes: string[] = []
    let character = params.character?.trim().toLowerCase()
    if (!character && type === 'classmod') {
      character = fx.meta.character
      notes.push(`no character given for a class-mod search; using ${character} (config)`)
    }
    let rows = fx.pool.filter((r) => {
      if (q && !r.name.toLowerCase().includes(q)) return false
      if (type && !TYPE_MATCH[type]?.(r)) return false
      if (params.element && (r.decoded.element ?? 'impact') !== params.element) return false
      if (man && !r.manufacturer.toLowerCase().includes(man)) return false
      if (rarity && (r.decoded.rarity ?? r.rarity).toLowerCase() !== rarity) return false
      if (character && !(r.weapon_type.includes(character) || r.source.toLowerCase().includes(character))) return false
      return true
    })
    const weaponish = !type || ['pistol', 'shotgun', 'smg', 'assaultrifle', 'ar', 'sniper', 'heavy', 'weapon'].includes(type)
    const hidden = []
    if (weaponish && rows.length >= 3) {
      if (params.include_unowned) {
        const extra = rows.slice(0, 2).map((r, i) => ({
          ...clone(r),
          serial: mutate(r.serial, `unowned${i}`),
          decoded: { ...r.decoded, owned: false, warnings: [`needs ${UNOWNED_PACK.label} (not owned)`] },
        }))
        rows = [...extra, ...rows]
      } else {
        hidden.push({ ...UNOWNED_PACK, count: 2 + (hash(JSON.stringify(params)) % 24) })
      }
    }
    const dropped = params.verify_element !== false && params.element === 'fire' ? 58 : params.element === 'shock' ? 23 : 0
    const level = params.level ?? null
    const results = rows.slice(0, limit).map((r) => (level === null ? r : { ...r, level }))
    return { count: results.length, level, results, hidden, dropped_element_mismatch: dropped, notes }
  }

  function transformed(base: IdentifyResponse, serial: string, note: string, edit: (p: IdentifyResponse) => void): TransformResponse {
    const next = clone(base)
    next.serial = serial
    next.info.serial = serial
    edit(next)
    remember(next)
    return { ...next, previous: base.serial, note }
  }

  function capturedTransform(req: TransformRequest): TransformResponse | null {
    const key =
      req.op === 'relevel' ? `relevel_${req.level}` :
      req.op === 'set_element' ? `set_element_${req.element}` :
      req.op === 'reseed' ? `reseed_${req.seed ?? 'x'}` :
      req.op === 'swap' ? `swap_${req.positions.join('_')}` : ''
    const hit = fx.transforms[key]
    if (!hit || typeof hit === 'string' || hit.previous !== req.serial) return null
    return hit
  }

  function doTransform(req: TransformRequest): TransformResponse {
    const base = lookup(req.serial)
    const captured = capturedTransform(req)
    if (captured) return clone(captured)
    switch (req.op) {
      case 'relevel': {
        if (!Number.isInteger(req.level) || req.level < 1 || req.level > 100) throw new ApiError('bad_request', 'level must be an integer 1-100', 400)
        return transformed(base, mutate(req.serial, `L${req.level}`), '', (p) => {
          p.info.level = req.level
        })
      }
      case 'set_element': {
        if (!base.can_set_element) {
          throw new ApiError('bad_request', `set_element is for weapons: ${base.info.display_name ?? 'this item'} (${base.info.category ?? 'unknown category'}) is gear and has no element`, 400)
        }
        return transformed(base, mutate(req.serial, `E${req.element}`), 'passed structural checks only', (p) => {
          p.info.element = req.element
          const at = p.parts.findIndex((part) => ELEMENT_LABELS.has(part.label))
          if (req.element === 'impact') {
            if (at >= 0) p.parts.splice(at, 1)
            p.parts = p.parts.map((part, i) => ({ ...part, position: i }))
          } else if (at >= 0) {
            const old = p.parts[at] as IdentifyPart
            p.parts[at] = { ...old, label: ELEMENT_PART_LABEL[req.element], raw: `part_${req.element}` }
          } else {
            p.parts.push({ position: p.parts.length, token_index: 99, label: ELEMENT_PART_LABEL[req.element], category_id: 1, index: 11, raw: `part_${req.element}`, category_link: null })
          }
        })
      }
      case 'reseed': {
        const seed = req.seed ?? Math.floor(Math.random() * 2 ** 31)
        return { ...transformed(base, mutate(req.serial, `S${seed}`), `seed ${seed} (was 1676)`, () => undefined), seed }
      }
      case 'swap': {
        const source = lookup(req.source)
        if (source.info.category_id !== base.info.category_id && !req.allow_cross) {
          throw new ApiError(
            'bad_request',
            `refusing to swap between different item categories: base is ${base.info.category} (${base.info.category_id}), source is ${source.info.category} (${source.info.category_id}). Plain part indices are category-relative, so the copied part would decode as something unrelated. Pass allow_cross only if you know the two categories share a parts table.`,
            400,
          )
        }
        for (const pos of req.positions) {
          if (!source.parts[pos]) throw new ApiError('serial_error', `position ${pos} is out of range (source has ${source.parts.length} parts)`, 400)
        }
        return transformed(base, mutate(req.serial, `W${req.positions.join(',')}${req.source}`), 'passed structural checks only; in-game validity is not guaranteed', (p) => {
          for (const pos of req.positions) {
            const from = source.parts[pos] as IdentifyPart
            if (p.parts[pos]) p.parts[pos] = { ...from, position: pos }
          }
        })
      }
    }
  }

  function doDiff(a: string, b: string): DiffRow[] {
    if (a === fx.diff.a && b === fx.diff.b) return clone(fx.diff.rows)
    const pa = lookup(a)
    const pb = lookup(b)
    const rows: DiffRow[] = []
    const fields = ['level', 'rarity', 'element', 'display_name', 'category'] as const
    for (const f of fields) if (pa.info[f] !== pb.info[f]) rows.push({ field: f, a: pa.info[f], b: pb.info[f] })
    const n = Math.max(pa.parts.length, pb.parts.length)
    for (let i = 0; i < n; i++) {
      const x = pa.parts[i]?.label ?? null
      const y = pb.parts[i]?.label ?? null
      if (x !== y) rows.push({ field: `part[${i}]`, a: x, b: y })
    }
    if (rows.length === 0 && a !== b) rows.push({ field: 'seed', a: 'original', b: 'rerolled' })
    return rows
  }

  function doBuild(body: BuildRequest): BuildResponse {
    if (scenario === 'sick') throw unavailable('builder')
    if (!Array.isArray(body.requests) || body.requests.length === 0) throw new ApiError('bad_request', 'requests must be a non-empty array', 400)
    const items: LoadoutItem[] = []
    const unmatched: string[] = []
    const warnings: string[] = []
    const groups: string[] = []
    body.requests.forEach((req, i) => {
      const group = req.group ?? (req.type && ['shield', 'classmod', 'repkit', 'grenade', 'enhancement'].includes(req.type) ? 'Gear' : 'Weapons')
      let picks: IdentifyResponse[] = []
      let row: SearchResultRow | undefined
      if (req.serial) {
        picks = [lookup(req.serial)]
        row = fx.pool.find((r) => r.serial === req.serial)
      } else {
        let character = req.character ?? undefined
        if (req.type === 'classmod' && !character) {
          character = fx.meta.character
          warnings.push(`entry ${i + 1}: class mod with no character, using ${character} (config)`)
        }
        const found = searchRows({
          query: req.query ?? undefined,
          type: req.type ?? undefined,
          element: (req.element as ElementId | undefined) ?? undefined,
          manufacturer: req.manufacturer ?? undefined,
          rarity: req.rarity ?? undefined,
          character,
          limit: req.count ?? 1,
        }).results
        if (found.length === 0) {
          unmatched.push([req.query, req.type, req.element].filter(Boolean).join(' / ') || `entry ${i + 1}`)
          return
        }
        row = found[0]
        picks = found.map((r) => known.get(r.serial)).filter((p): p is IdentifyResponse => Boolean(p))
        if (picks.length === 0) {
          unmatched.push(`${req.query ?? req.type ?? 'entry'} (mock has no decoded sample)`)
          return
        }
      }
      if (!groups.includes(group)) groups.push(group)
      for (const p of picks) {
        const level = body.level ?? p.info.level
        const name = req.name || row?.name || p.info.display_name || 'Item'
        items.push({
          name,
          serial: p.serial,
          level,
          group,
          display_name: req.display_name ?? null,
          manufacturer: row?.manufacturer ?? '',
          label: req.label ?? row?.label ?? '',
          type: row?.type ?? '',
          weapon_type: row?.weapon_type ?? '',
          rarity: p.info.rarity ?? '',
          element: p.info.element,
          category: p.info.category,
          legendary_name: p.info.legendary_name,
          parts: p.parts.map((part) => part.label),
          odds: p.odds,
          source: row?.source ?? '',
          note: req.note ?? '',
          warnings: [...p.info.warnings, ...p.problems],
          shown_name: req.display_name || p.info.legendary_name || name,
        })
      }
    })
    const loadout = { title: body.title || 'Break Free Loadout', level: body.level ?? null, groups, unmatched, warnings, items }
    return { loadout, html: renderMockSheet(loadout), text: renderMockText(loadout) }
  }

  return {
    async meta(opts) {
      await wait(opts, 120)
      return clone(fx.meta)
    },
    async health(opts) {
      await wait(opts, 200)
      return health()
    },
    async stats(opts) {
      await wait(opts)
      if (scenario === 'sick') throw unavailable('catalog')
      return clone(fx.stats)
    },
    async search(params, opts) {
      await wait(opts)
      if (scenario === 'sick') throw unavailable('catalog')
      return clone(searchRows(params))
    },
    async identify(body, opts) {
      await wait(opts)
      const payload = clone(lookup(body.serial))
      if (body.level !== undefined) {
        payload.serial = mutate(payload.serial, `L${body.level}`)
        payload.info.serial = payload.serial
        payload.info.level = body.level
        remember(clone(payload))
      }
      return payload
    },
    async transform(body, opts) {
      await wait(opts)
      return clone(doTransform(body))
    },
    async diff(a, b, opts) {
      await wait(opts, 120)
      return { rows: doDiff(a, b) }
    },
    async build(body, opts) {
      await wait(opts, 500)
      return doBuild(body)
    },
  }
}

function stripTransform(t: TransformResponse): IdentifyResponse {
  return {
    serial: t.serial,
    info: t.info,
    odds: t.odds,
    parts: t.parts,
    problems: t.problems,
    is_weapon: t.is_weapon,
    can_set_element: t.can_set_element,
  }
}
