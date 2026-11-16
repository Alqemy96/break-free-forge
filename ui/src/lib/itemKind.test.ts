import { describe, expect, it } from 'vitest'
import { ICON_KINDS, iconKindOf } from './itemKind'

describe('iconKindOf', () => {
  it('uses weapon_type first', () => {
    expect(iconKindOf({ type: 'weapon', weaponType: 'assaultrifle' })).toBe('assault_rifle')
    expect(iconKindOf({ type: 'weapon', weaponType: 'smg' })).toBe('smg')
    expect(iconKindOf({ type: 'weapon', weaponType: 'heavy' })).toBe('heavy')
  })
  it('falls back to the item type', () => {
    expect(iconKindOf({ type: 'shield', weaponType: '' })).toBe('shield')
    expect(iconKindOf({ type: 'repair_kit' })).toBe('repkit')
    expect(iconKindOf({ type: 'gadget' })).toBe('grenade')
    expect(iconKindOf({ type: 'classmod' })).toBe('classmod')
    expect(iconKindOf({ type: 'enhancement' })).toBe('enhancement')
  })
  it('reads the decoded category text', () => {
    expect(iconKindOf({ category: 'Assault Rifle' })).toBe('assault_rifle')
    expect(iconKindOf({ category: 'Sniper Rifle' })).toBe('sniper')
    expect(iconKindOf({ category: 'Class Mod (Demo)' })).toBe('classmod')
  })
  it('never guesses: unknown input is the generic icon', () => {
    expect(iconKindOf({})).toBe('unknown')
    expect(iconKindOf({ type: 'weapon' })).toBe('unknown')
    expect(iconKindOf({ category: 'Mystery Box' })).toBe('unknown')
  })
  it('lists every kind once', () => {
    expect(new Set(ICON_KINDS).size).toBe(ICON_KINDS.length)
  })
})
