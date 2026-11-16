import { describe, expect, it } from 'vitest'
import type { IdentifyResponse, TransformResponse } from '@/api/types'
import { currentEntry, emptyWorkbench, workbenchReducer } from './workbench'

const payload = (serial: string, level = 60): IdentifyResponse => ({
  serial,
  info: {
    serial,
    category_id: 11,
    category: 'Tediore Shotgun',
    level,
    rarity: 'Legendary',
    element: 'cryo',
    legendary_name: 'Anarchy',
    display_name: 'Anarchy',
    parts: [],
    other_components: [],
    tokens: '',
    content_pack: 'coregame',
    content_pack_label: 'Base game',
    owned: true,
    manifest_ok: true,
    warnings: [],
  },
  odds: '',
  parts: [],
  problems: [],
  is_weapon: true,
  can_set_element: true,
})

const transformed = (serial: string, previous: string): TransformResponse => ({ ...payload(serial, 50), previous, note: 'n' })

describe('workbenchReducer', () => {
  it('a fresh identify resets the stack', () => {
    let s = workbenchReducer(emptyWorkbench, { type: 'loaded', payload: payload('@Ua') })
    s = workbenchReducer(s, { type: 'loaded', payload: payload('@Ub') })
    expect(s.stack.map((e) => e.payload.serial)).toEqual(['@Ub'])
    expect(currentEntry(s)?.label).toBe('identified')
  })

  it('proposes, attaches the diff, accepts and undoes', () => {
    let s = workbenchReducer(emptyWorkbench, { type: 'loaded', payload: payload('@Ua') })
    s = workbenchReducer(s, { type: 'proposed', result: transformed('@Ub', '@Ua'), label: 're-level to 50' })
    expect(s.pending?.diff).toBeNull()
    expect(workbenchReducer(s, { type: 'diffLoaded', serial: '@Uz', rows: [] })).toBe(s)
    s = workbenchReducer(s, { type: 'diffLoaded', serial: '@Ub', rows: [{ field: 'level', a: 60, b: 50 }] })
    expect(s.pending?.diff).toHaveLength(1)
    s = workbenchReducer(s, { type: 'accept' })
    expect(s.pending).toBeNull()
    expect(s.stack.map((e) => e.label)).toEqual(['identified', 're-level to 50'])
    expect(currentEntry(s)?.payload).not.toHaveProperty('previous')
    s = workbenchReducer(s, { type: 'undo' })
    expect(currentEntry(s)?.payload.serial).toBe('@Ua')
    expect(workbenchReducer(s, { type: 'undo' })).toBe(s)
  })

  it('discard drops the proposal and keeps history', () => {
    let s = workbenchReducer(emptyWorkbench, { type: 'loaded', payload: payload('@Ua') })
    s = workbenchReducer(s, { type: 'proposed', result: transformed('@Ub', '@Ua'), label: 'x' })
    s = workbenchReducer(s, { type: 'discard' })
    expect(s.pending).toBeNull()
    expect(s.stack).toHaveLength(1)
  })

  it('records a diff failure as an empty diff with the message', () => {
    let s = workbenchReducer(emptyWorkbench, { type: 'loaded', payload: payload('@Ua') })
    s = workbenchReducer(s, { type: 'proposed', result: transformed('@Ub', '@Ua'), label: 'x' })
    s = workbenchReducer(s, { type: 'diffFailed', serial: '@Ub', message: 'boom' })
    expect(s.pending).toMatchObject({ diff: [], diffError: 'boom' })
  })

  it('ignores a proposal with nothing loaded', () => {
    expect(workbenchReducer(emptyWorkbench, { type: 'proposed', result: transformed('@Ub', '@Ua'), label: 'x' })).toBe(emptyWorkbench)
  })
})
