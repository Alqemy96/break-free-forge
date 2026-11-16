/** Parse the legacy JSON loadout spec (the cli's `--spec` file) for Quick build. Pure, unit-tested. */
import type { LoadoutRequest } from '@/api/types'

const STRING_FIELDS = [
  'group',
  'serial',
  'query',
  'type',
  'element',
  'manufacturer',
  'rarity',
  'character',
  'note',
  'display_name',
  'label',
  'name',
] as const

const KNOWN = new Set<string>([...STRING_FIELDS, 'count', 'label_name'])

export type SpecParse =
  | { ok: true; requests: LoadoutRequest[]; notes: string[] }
  | { ok: false; error: string }

export function parseSpec(text: string): SpecParse {
  const trimmed = text.trim()
  if (!trimmed) return { ok: false, error: 'Paste a JSON array of loadout entries first.' }
  let data: unknown
  try {
    data = JSON.parse(trimmed)
  } catch (err) {
    const reason = err instanceof Error ? err.message : 'parse error'
    return { ok: false, error: `Not valid JSON (${reason}).` }
  }
  if (data && typeof data === 'object' && !Array.isArray(data) && Array.isArray((data as { requests?: unknown }).requests)) {
    data = (data as { requests: unknown[] }).requests
  }
  if (!Array.isArray(data)) return { ok: false, error: 'The spec must be a JSON array of objects.' }
  if (data.length === 0) return { ok: false, error: 'The spec is empty: list at least one item.' }

  const requests: LoadoutRequest[] = []
  const notes: string[] = []
  for (const [i, entry] of data.entries()) {
    const where = `entry ${i + 1}`
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
      return { ok: false, error: `${where} must be a JSON object.` }
    }
    const obj = entry as Record<string, unknown>
    const req: LoadoutRequest = {}
    for (const field of STRING_FIELDS) {
      const value = obj[field]
      if (value === undefined || value === null) continue
      if (typeof value !== 'string') return { ok: false, error: `${where}: "${field}" must be a string.` }
      if (field === 'serial' && value !== value.trim()) {
        return { ok: false, error: `${where}: "serial" has leading or trailing spaces.` }
      }
      req[field] = value
    }
    if (req.display_name === undefined && typeof obj.label_name === 'string' && obj.label_name) {
      req.display_name = obj.label_name
    }
    if (obj.count !== undefined) {
      const count = Number(obj.count)
      if (!Number.isInteger(count) || count < 1) return { ok: false, error: `${where}: "count" must be a whole number >= 1.` }
      req.count = count
    }
    const unknown = Object.keys(obj).filter((k) => !KNOWN.has(k))
    if (unknown.length) notes.push(`${where}: ignoring unknown key(s) ${unknown.sort().join(', ')}`)
    requests.push(req)
  }
  return { ok: true, requests, notes }
}
