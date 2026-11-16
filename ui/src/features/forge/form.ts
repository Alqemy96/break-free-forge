/** Forge search form <-> API params <-> URL hash. Pure, unit-tested. */
import type { SearchParams } from '@/api/types'
import { clampLimit, elementKey, parseLevel } from '@/lib/format'

export interface SearchForm {
  query: string
  type: string
  element: string
  rarity: string
  manufacturer: string
  character: string
  /** null: keep each code's stored level */
  level: number | null
  limit: number
  includeUnowned: boolean
  verifyElement: boolean
}

export function defaultForm(level: number | null): SearchForm {
  return {
    query: '',
    type: '',
    element: '',
    rarity: '',
    manufacturer: '',
    character: '',
    level,
    limit: 25,
    includeUnowned: false,
    verifyElement: true,
  }
}

export function toSearchParams(form: SearchForm): SearchParams {
  const params: SearchParams = { limit: clampLimit(form.limit) }
  if (form.query.trim()) params.query = form.query.trim()
  if (form.type) params.type = form.type
  const element = elementKey(form.element)
  if (element) params.element = element
  if (form.rarity) params.rarity = form.rarity
  if (form.manufacturer.trim()) params.manufacturer = form.manufacturer.trim()
  if (form.character) params.character = form.character
  if (form.level !== null) params.level = form.level
  if (form.includeUnowned) params.include_unowned = true
  if (!form.verifyElement) params.verify_element = false
  return params
}

/** Hash params (short keys) for a shareable/restorable search. */
export function formToHash(form: SearchForm): Record<string, string | number | boolean | null> {
  return {
    q: form.query.trim() || null,
    type: form.type || null,
    element: form.element || null,
    rarity: form.rarity || null,
    man: form.manufacturer.trim() || null,
    char: form.character || null,
    level: form.level === null ? 'keep' : form.level,
    limit: form.limit === 25 ? null : form.limit,
    unowned: form.includeUnowned || null,
    noverify: !form.verifyElement || null,
  }
}

export function formFromHash(params: Record<string, string>, fallbackLevel: number | null): SearchForm {
  const base = defaultForm(fallbackLevel)
  const level = params.level === 'keep' ? null : (parseLevel(params.level) ?? fallbackLevel)
  return {
    ...base,
    query: params.q ?? '',
    type: params.type ?? '',
    element: elementKey(params.element) ?? '',
    rarity: params.rarity ?? '',
    manufacturer: params.man ?? '',
    character: params.char ?? '',
    level,
    limit: params.limit ? clampLimit(params.limit) : 25,
    includeUnowned: params.unowned === '1',
    verifyElement: params.noverify !== '1',
  }
}

/** True when the hash describes a search worth running on arrival. */
export function hashHasSearch(params: Record<string, string>): boolean {
  return ['q', 'type', 'element', 'rarity', 'man', 'char'].some((k) => Boolean(params[k]))
}
