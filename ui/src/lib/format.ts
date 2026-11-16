/** Pure formatting helpers. No React, no DOM: unit-tested in format.test.ts. */
import { ELEMENT_IDS, type ElementId, type HiddenPack, type JsonValue } from '@/api/types'

export type RarityKey = 'common' | 'uncommon' | 'rare' | 'epic' | 'legendary' | 'pearl' | 'vile' | 'unknown'

const RARITY_KEYS: Record<string, RarityKey> = {
  common: 'common',
  uncommon: 'uncommon',
  rare: 'rare',
  epic: 'epic',
  legendary: 'legendary',
  pearl: 'pearl',
  pearlescent: 'pearl',
  vile: 'vile',
}

/** 'Legendary' -> 'legendary'; anything unknown (or missing) -> 'unknown'. */
export function rarityKey(rarity: string | null | undefined): RarityKey {
  if (!rarity) return 'unknown'
  return RARITY_KEYS[rarity.trim().toLowerCase()] ?? 'unknown'
}

export const RARITY_ORDER: RarityKey[] = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'pearl', 'vile']

const ELEMENT_ALIASES: Record<string, ElementId> = {
  cryo: 'cryo',
  ice: 'cryo',
  fire: 'fire',
  incendiary: 'fire',
  burn: 'fire',
  radiation: 'radiation',
  rad: 'radiation',
  shock: 'shock',
  electric: 'shock',
  lightning: 'shock',
  corrosive: 'corrosive',
  corrosion: 'corrosive',
  acid: 'corrosive',
  impact: 'impact',
  kinetic: 'impact',
  'non-elemental': 'impact',
}

/** Same aliases as core/vocab.py; null for empty or unknown input (never throws in the UI). */
export function elementKey(element: string | null | undefined): ElementId | null {
  if (!element) return null
  return ELEMENT_ALIASES[element.trim().toLowerCase()] ?? null
}

export function isElementId(value: unknown): value is ElementId {
  return typeof value === 'string' && (ELEMENT_IDS as readonly string[]).includes(value)
}

const ELEMENT_LABELS: Record<ElementId, string> = {
  cryo: 'Cryo',
  fire: 'Fire',
  radiation: 'Radiation',
  shock: 'Shock',
  corrosive: 'Corrosive',
  impact: 'Impact',
}

export function elementLabel(element: string | null | undefined): string {
  const key = elementKey(element)
  return key ? ELEMENT_LABELS[key] : 'No element'
}

/** 9875 -> "9,875" (fixed en-US grouping so the header never jitters between locales). */
export function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-'
  return Math.trunc(value).toLocaleString('en-US')
}

export function plural(count: number, word: string, many?: string): string {
  return `${formatInt(count)} ${count === 1 ? word : (many ?? `${word}s`)}`
}

/** Keep both ends of a serial visible: '@Uge(J0Fnkb...q0%7$'. */
export function truncateSerial(serial: string, head = 12, tail = 6): string {
  if (serial.length <= head + tail + 1) return serial
  return `${serial.slice(0, head)}…${serial.slice(-tail)}`
}

/** Level input text -> 1..100 integer, or null for blank/invalid. */
export function parseLevel(text: string | number | null | undefined): number | null {
  if (text === null || text === undefined) return null
  const raw = typeof text === 'number' ? text : Number(String(text).trim() || NaN)
  if (!Number.isFinite(raw)) return null
  const n = Math.trunc(raw)
  return n >= 1 && n <= 100 ? n : null
}

/** Search limit: 1..200 (contract), default 25. */
export function clampLimit(value: number | string | null | undefined, fallback = 25): number {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return fallback
  return Math.min(200, Math.max(1, Math.trunc(n)))
}

/** "26 hidden: needs Expansion Pack 3 - Example Title" (one line per pack). */
export function hiddenLine(pack: HiddenPack): string {
  return `${formatInt(pack.count)} hidden: needs ${pack.label || pack.pack}`
}

export function hiddenTotal(hidden: readonly HiddenPack[]): number {
  return hidden.reduce((sum, h) => sum + (Number.isFinite(h.count) ? h.count : 0), 0)
}

/** Human form of one diff cell. */
export function formatDiffValue(value: JsonValue | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (Array.isArray(value)) return value.length ? value.map((v) => formatDiffValue(v)).join(', ') : '—'
  return JSON.stringify(value)
}

/** 'Cryo Locksmith!' -> 'cryo-locksmith' (download file names). */
export function slugify(text: string, fallback = 'loadout'): string {
  const slug = text
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
  return slug || fallback
}

/** Weapons go to the Weapons group by default, everything else is Gear. */
export function kindOfType(type: string | null | undefined, isWeapon?: boolean): 'weapon' | 'gear' {
  if (isWeapon !== undefined) return isWeapon ? 'weapon' : 'gear'
  return (type ?? '').toLowerCase() === 'weapon' ? 'weapon' : 'gear'
}

/** "classmod_locksmith" -> "Classmod Locksmith"; used where the server gives raw tokens. */
export function titleCase(text: string): string {
  return text
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

/** "dark_siren" -> "Dark Siren" */
export function characterLabel(id: string): string {
  return titleCase(id)
}

/** Where two serials differ: shared prefix/suffix plus the changed middles (for highlighting). */
export function serialDiffParts(a: string, b: string): { prefix: string; aMid: string; bMid: string; suffix: string } {
  let start = 0
  while (start < a.length && start < b.length && a[start] === b[start]) start++
  let end = 0
  while (end < a.length - start && end < b.length - start && a[a.length - 1 - end] === b[b.length - 1 - end]) end++
  return {
    prefix: a.slice(0, start),
    aMid: a.slice(start, a.length - end),
    bMid: b.slice(start, b.length - end),
    suffix: end ? a.slice(a.length - end) : '',
  }
}

/** Server sentences sometimes lack a final stop; add one before appending more text. */
export function sentence(text: string): string {
  const t = text.trim()
  return !t || /[.!?)]$/.test(t) ? t : `${t}.`
}
