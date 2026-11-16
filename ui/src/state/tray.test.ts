import { describe, expect, it } from 'vitest'
import { initialTray, orderedItems, parseTrayState, toBuildRequest, trayCodesText, trayReducer, type NewTrayItem, type TrayState } from './tray'

const item = (id: string, kind: 'weapon' | 'gear' = 'weapon', extra: Partial<NewTrayItem> = {}): NewTrayItem => ({
  id,
  serial: `@U${id}`,
  name: `Item ${id}`,
  label: 'Jakobs Pistol',
  rarity: 'Legendary',
  element: kind === 'weapon' ? 'cryo' : null,
  level: 60,
  kind,
  ...extra,
})

const add = (state: TrayState, ...items: NewTrayItem[]) => items.reduce((s, it) => trayReducer(s, { type: 'add', item: it }), state)

describe('trayReducer', () => {
  it('adds weapons to Weapons and everything else to Gear', () => {
    const s = add(initialTray(60), item('a'), item('b', 'gear'))
    expect(s.items.map((i) => [i.id, i.group])).toEqual([
      ['a', 'Weapons'],
      ['b', 'Gear'],
    ])
  })

  it('ignores a serial that is already in the tray', () => {
    const s = add(initialTray(), item('a'))
    expect(trayReducer(s, { type: 'add', item: { ...item('a'), id: 'other' } })).toBe(s)
  })

  it('creates a group named on add', () => {
    const s = add(initialTray(), item('a', 'weapon', { group: 'Swap set' }))
    expect(s.groups).toEqual(['Weapons', 'Gear', 'Swap set'])
  })

  it('moves within a group, skipping items of other groups', () => {
    let s = add(initialTray(), item('w1'), item('g1', 'gear'), item('w2'))
    s = trayReducer(s, { type: 'move', id: 'w2', direction: -1 })
    expect(orderedItems(s).map((i) => i.id)).toEqual(['w2', 'w1', 'g1'])
    expect(trayReducer(s, { type: 'move', id: 'w2', direction: -1 })).toBe(s)
  })

  it('reorders a group from a drag result and rejects a stale order', () => {
    let s = add(initialTray(), item('a'), item('b'), item('c'), item('g', 'gear'))
    s = trayReducer(s, { type: 'reorder', group: 'Weapons', ids: ['c', 'a', 'b'] })
    expect(orderedItems(s).map((i) => i.id)).toEqual(['c', 'a', 'b', 'g'])
    expect(trayReducer(s, { type: 'reorder', group: 'Weapons', ids: ['c', 'a'] })).toBe(s)
  })

  it('regroups an item to the end of its new group', () => {
    let s = add(initialTray(), item('a'), item('b', 'gear'), item('c', 'gear'))
    s = trayReducer(s, { type: 'setGroup', id: 'a', group: 'Gear' })
    expect(orderedItems(s).map((i) => `${i.group}:${i.id}`)).toEqual(['Gear:b', 'Gear:c', 'Gear:a'])
  })

  it('edits display name and note', () => {
    let s = add(initialTray(), item('a'))
    s = trayReducer(s, { type: 'update', id: 'a', patch: { displayName: 'Ice Party', note: 'main gun' } })
    expect(s.items[0]).toMatchObject({ displayName: 'Ice Party', note: 'main gun' })
  })

  it('removes items', () => {
    const s = trayReducer(add(initialTray(), item('a'), item('b')), { type: 'remove', id: 'a' })
    expect(s.items.map((i) => i.id)).toEqual(['b'])
  })

  it('renames, merges, reorders and removes groups', () => {
    let s = add(initialTray(), item('a'), item('g', 'gear'))
    s = trayReducer(s, { type: 'renameGroup', from: 'Weapons', to: 'Guns' })
    expect(s.groups).toEqual(['Guns', 'Gear'])
    expect(s.items[0]?.group).toBe('Guns')
    s = trayReducer(s, { type: 'moveGroup', name: 'Gear', direction: -1 })
    expect(s.groups).toEqual(['Gear', 'Guns'])
    expect(trayReducer(s, { type: 'removeGroup', name: 'Guns' })).toBe(s)
    s = trayReducer(s, { type: 'renameGroup', from: 'Guns', to: 'Gear' })
    expect(s.groups).toEqual(['Gear'])
    expect(s.items.every((i) => i.group === 'Gear')).toBe(true)
    s = trayReducer(trayReducer(s, { type: 'remove', id: 'a' }), { type: 'remove', id: 'g' })
    expect(trayReducer(s, { type: 'removeGroup', name: 'Gear' }).groups).toEqual(['Gear'])
  })

  it('clears items and restores default groups', () => {
    const s = trayReducer(add(initialTray(), item('a', 'weapon', { group: 'X' })), { type: 'clear' })
    expect(s.items).toEqual([])
    expect(s.groups).toEqual(['Weapons', 'Gear'])
  })
})

describe('toBuildRequest', () => {
  it('emits explicit-serial requests in group order with overrides', () => {
    let s = add(initialTray(50), item('g', 'gear'), item('w'))
    s = trayReducer(s, { type: 'update', id: 'w', patch: { displayName: '  Ice Party ', note: '' } })
    s = trayReducer(s, { type: 'setTitle', title: 'Cryo build' })
    expect(toBuildRequest(s)).toEqual({
      title: 'Cryo build',
      level: 50,
      requests: [
        { group: 'Weapons', serial: '@Uw', display_name: 'Ice Party', name: 'Item w', label: 'Jakobs Pistol' },
        { group: 'Gear', serial: '@Ug', name: 'Item g', label: 'Jakobs Pistol' },
      ],
    })
  })

  it('omits level when the tray keeps stored levels', () => {
    const s = add(initialTray(null), item('a'))
    expect('level' in toBuildRequest(s)).toBe(false)
  })

  it('lists every code for Copy all codes', () => {
    const s = add(initialTray(), item('a'), item('b', 'gear'))
    expect(trayCodesText(s)).toBe('Item a\n@Ua\n\nItem b\n@Ub')
  })
})

describe('parseTrayState', () => {
  it('round-trips a valid state', () => {
    const s = add(initialTray(60), item('a'), item('b', 'gear'))
    expect(parseTrayState(JSON.parse(JSON.stringify(s)))).toEqual(s)
  })

  it('rejects garbage and repairs partial data', () => {
    expect(parseTrayState(null)).toBeNull()
    expect(parseTrayState({ version: 2, items: [], groups: [] })).toBeNull()
    const repaired = parseTrayState({
      version: 1,
      title: 7,
      level: 'x',
      groups: [],
      items: [{ id: 'a', serial: '@Ua', group: 'Mine', element: 'electric' }, { id: 'b' }, { id: 'c', serial: '@Ua' }],
    })
    expect(repaired?.items).toHaveLength(1)
    expect(repaired?.items[0]).toMatchObject({ group: 'Mine', element: 'shock', kind: 'gear', displayName: '' })
    expect(repaired?.groups).toEqual(['Mine'])
    expect(repaired?.level).toBeNull()
    expect(repaired?.title).toBe('Break Free Loadout')
  })
})
