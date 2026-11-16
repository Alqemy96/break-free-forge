/**
 * The loadout tray: a pure reducer (unit-tested) over an ordered list of explicit-serial items in
 * named groups. `toBuildRequest` turns it into the /api/build body, so a rebuild after any
 * reorder/regroup/remove is a single call.
 */
import type { BuildRequest, ElementId, LoadoutRequest } from '@/api/types'
import { elementKey } from '@/lib/format'
import { ICON_KINDS, type IconKind } from '@/lib/itemKind'

export const DEFAULT_GROUPS = ['Weapons', 'Gear'] as const
export const DEFAULT_TITLE = 'Break Free Loadout'

export interface TrayItem {
  id: string
  serial: string
  /** catalog or decoded name (sent as the request's `name` hint) */
  name: string
  /** "Tediore Shotgun" (sent as `label`) */
  label: string
  rarity: string | null
  element: ElementId | null
  level: number | null
  kind: 'weapon' | 'gear'
  /** silhouette to draw (optional: older saved trays have none) */
  icon?: IconKind
  /** maker name, drives the generic maker mark (optional) */
  maker?: string
  group: string
  /** optional override shown on the sheet; '' = none */
  displayName: string
  note: string
}

export interface TrayState {
  version: 1
  title: string
  /** null: keep each code's own level */
  level: number | null
  groups: string[]
  items: TrayItem[]
}

export type NewTrayItem = Omit<TrayItem, 'group' | 'displayName' | 'note'> &
  Partial<Pick<TrayItem, 'group' | 'displayName' | 'note'>>

export type TrayAction =
  | { type: 'add'; item: NewTrayItem }
  | { type: 'remove'; id: string }
  | { type: 'update'; id: string; patch: Partial<Pick<TrayItem, 'displayName' | 'note'>> }
  | { type: 'move'; id: string; direction: -1 | 1 }
  | { type: 'reorder'; group: string; ids: string[] }
  | { type: 'setGroup'; id: string; group: string }
  | { type: 'addGroup'; name: string }
  | { type: 'renameGroup'; from: string; to: string }
  | { type: 'removeGroup'; name: string }
  | { type: 'moveGroup'; name: string; direction: -1 | 1 }
  | { type: 'setTitle'; title: string }
  | { type: 'setLevel'; level: number | null }
  | { type: 'clear' }
  | { type: 'replace'; state: TrayState }

export function initialTray(level: number | null = null): TrayState {
  return { version: 1, title: DEFAULT_TITLE, level, groups: [...DEFAULT_GROUPS], items: [] }
}

const cleanName = (name: string) => name.replace(/\s+/g, ' ').trim().slice(0, 40)

function defaultGroupFor(state: TrayState, kind: TrayItem['kind']): string {
  const wanted = kind === 'weapon' ? 'Weapons' : 'Gear'
  if (state.groups.includes(wanted)) return wanted
  return state.groups[kind === 'weapon' ? 0 : state.groups.length - 1] ?? wanted
}

function ensureGroup(groups: string[], name: string): string[] {
  return groups.includes(name) ? groups : [...groups, name]
}

function swap<T>(list: T[], i: number, j: number): T[] {
  const next = [...list]
  const a = next[i]
  const b = next[j]
  if (a === undefined || b === undefined) return list
  next[i] = b
  next[j] = a
  return next
}

export function trayReducer(state: TrayState, action: TrayAction): TrayState {
  switch (action.type) {
    case 'add': {
      if (state.items.some((it) => it.serial === action.item.serial)) return state
      const group = action.item.group ? cleanName(action.item.group) || defaultGroupFor(state, action.item.kind) : defaultGroupFor(state, action.item.kind)
      const item: TrayItem = { displayName: '', note: '', ...action.item, group }
      return { ...state, groups: ensureGroup(state.groups, group), items: [...state.items, item] }
    }
    case 'remove': {
      const items = state.items.filter((it) => it.id !== action.id)
      return items.length === state.items.length ? state : { ...state, items }
    }
    case 'update': {
      let changed = false
      const items = state.items.map((it) => {
        if (it.id !== action.id) return it
        changed = true
        return { ...it, ...action.patch }
      })
      return changed ? { ...state, items } : state
    }
    case 'move': {
      const index = state.items.findIndex((it) => it.id === action.id)
      const item = state.items[index]
      if (!item) return state
      // the neighbour in the same group, in the requested direction
      let j = index + action.direction
      while (j >= 0 && j < state.items.length && state.items[j]?.group !== item.group) j += action.direction
      if (j < 0 || j >= state.items.length) return state
      return { ...state, items: swap(state.items, index, j) }
    }
    case 'reorder': {
      const inGroup = state.items.filter((it) => it.group === action.group)
      const byId = new Map(inGroup.map((it) => [it.id, it]))
      if (action.ids.length !== inGroup.length || !action.ids.every((id) => byId.has(id))) return state
      const ordered = action.ids.map((id) => byId.get(id) as TrayItem)
      let k = 0
      const items = state.items.map((it) => (it.group === action.group ? (ordered[k++] as TrayItem) : it))
      return { ...state, items }
    }
    case 'setGroup': {
      const group = cleanName(action.group)
      const item = state.items.find((it) => it.id === action.id)
      if (!item || !group || item.group === group) return state
      const rest = state.items.filter((it) => it.id !== action.id)
      return { ...state, groups: ensureGroup(state.groups, group), items: [...rest, { ...item, group }] }
    }
    case 'addGroup': {
      const name = cleanName(action.name)
      if (!name || state.groups.includes(name)) return state
      return { ...state, groups: [...state.groups, name] }
    }
    case 'renameGroup': {
      const to = cleanName(action.to)
      if (!to || !state.groups.includes(action.from) || action.from === to) return state
      if (state.groups.includes(to)) {
        // merging into an existing group
        return {
          ...state,
          groups: state.groups.filter((g) => g !== action.from),
          items: state.items.map((it) => (it.group === action.from ? { ...it, group: to } : it)),
        }
      }
      return {
        ...state,
        groups: state.groups.map((g) => (g === action.from ? to : g)),
        items: state.items.map((it) => (it.group === action.from ? { ...it, group: to } : it)),
      }
    }
    case 'removeGroup': {
      // only empty groups can go, and at least one group always stays
      if (!state.groups.includes(action.name) || state.groups.length <= 1) return state
      if (state.items.some((it) => it.group === action.name)) return state
      return { ...state, groups: state.groups.filter((g) => g !== action.name) }
    }
    case 'moveGroup': {
      const i = state.groups.indexOf(action.name)
      const j = i + action.direction
      if (i < 0 || j < 0 || j >= state.groups.length) return state
      return { ...state, groups: swap(state.groups, i, j) }
    }
    case 'setTitle':
      return state.title === action.title ? state : { ...state, title: action.title.slice(0, 120) }
    case 'setLevel':
      return state.level === action.level ? state : { ...state, level: action.level }
    case 'clear':
      return { ...state, items: [], groups: [...DEFAULT_GROUPS] }
    case 'replace':
      return action.state
    default:
      return state
  }
}

/** Items in display order: group order first, then insertion order inside a group. */
export function orderedItems(state: TrayState): TrayItem[] {
  const out: TrayItem[] = []
  for (const g of state.groups) for (const it of state.items) if (it.group === g) out.push(it)
  // orphans (group missing from the list) last, never dropped
  for (const it of state.items) if (!state.groups.includes(it.group)) out.push(it)
  return out
}

export function itemsInGroup(state: TrayState, group: string): TrayItem[] {
  return state.items.filter((it) => it.group === group)
}

/** The tray as an /api/build body: explicit-serial requests only. */
export function toBuildRequest(state: TrayState): BuildRequest {
  const requests: LoadoutRequest[] = orderedItems(state).map((it) => {
    const req: LoadoutRequest = { group: it.group, serial: it.serial }
    if (it.displayName.trim()) req.display_name = it.displayName.trim()
    if (it.note.trim()) req.note = it.note.trim()
    if (it.name) req.name = it.name
    if (it.label) req.label = it.label
    return req
  })
  const body: BuildRequest = { requests, title: state.title.trim() || DEFAULT_TITLE }
  if (state.level !== null) body.level = state.level
  return body
}

/** Plain list of every code in the tray (Copy all codes, before any build). */
export function trayCodesText(state: TrayState): string {
  return orderedItems(state)
    .map((it) => `${it.displayName.trim() || it.name}\n${it.serial}`)
    .join('\n\n')
}

/** Validate persisted JSON; anything malformed yields null (start fresh, never crash). */
export function parseTrayState(raw: unknown): TrayState | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  if (obj.version !== 1 || !Array.isArray(obj.items) || !Array.isArray(obj.groups)) return null
  const groups = obj.groups.filter((g): g is string => typeof g === 'string' && g.trim() !== '')
  const items: TrayItem[] = []
  const seen = new Set<string>()
  for (const entry of obj.items) {
    if (!entry || typeof entry !== 'object') continue
    const it = entry as Record<string, unknown>
    if (typeof it.id !== 'string' || typeof it.serial !== 'string' || !it.serial || seen.has(it.serial)) continue
    seen.add(it.serial)
    const group = typeof it.group === 'string' && it.group.trim() ? it.group : 'Gear'
    if (!groups.includes(group)) groups.push(group)
    items.push({
      id: it.id,
      serial: it.serial,
      name: typeof it.name === 'string' ? it.name : '',
      label: typeof it.label === 'string' ? it.label : '',
      rarity: typeof it.rarity === 'string' ? it.rarity : null,
      element: typeof it.element === 'string' ? elementKey(it.element) : null,
      level: typeof it.level === 'number' && Number.isFinite(it.level) ? it.level : null,
      kind: it.kind === 'weapon' ? 'weapon' : 'gear',
      ...(typeof it.icon === 'string' && (ICON_KINDS as readonly string[]).includes(it.icon) ? { icon: it.icon as IconKind } : {}),
      ...(typeof it.maker === 'string' && it.maker ? { maker: it.maker } : {}),
      group,
      displayName: typeof it.displayName === 'string' ? it.displayName : '',
      note: typeof it.note === 'string' ? it.note : '',
    })
  }
  if (groups.length === 0) groups.push(...DEFAULT_GROUPS)
  const level = typeof obj.level === 'number' && Number.isFinite(obj.level) ? obj.level : null
  const title = typeof obj.title === 'string' ? obj.title : DEFAULT_TITLE
  return { version: 1, title, level, groups, items }
}
