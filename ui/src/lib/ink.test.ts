import { describe, expect, it } from 'vitest'
import { inkModeFrom, isSlow } from './ink'

describe('ink mode', () => {
  it('url wins over storage', () => {
    expect(inkModeFrom('?ink=lite', null)).toBe('lite')
    expect(inkModeFrom('?ink=full', 'lite')).toBe('full')
  })
  it('stored lite sticks, otherwise auto', () => {
    expect(inkModeFrom('', 'lite')).toBe('lite')
    expect(inkModeFrom('', null)).toBe('auto')
    expect(inkModeFrom('?ink=bogus', 'other')).toBe('auto')
  })
  it('judges slowness by the average frame time', () => {
    expect(isSlow([16, 17, 16])).toBe(false)
    expect(isSlow([40, 45, 38])).toBe(true)
    expect(isSlow([])).toBe(false)
  })
})
