import { describe, expect, it } from 'vitest'
import { buildHash, parseHash } from './route'

describe('route', () => {
  it('parses screens and params', () => {
    expect(parseHash('#/workbench?serial=%40Uabc')).toEqual({ screen: 'workbench', params: { serial: '@Uabc' } })
    expect(parseHash('#/health')).toEqual({ screen: 'health', params: {} })
    expect(parseHash('')).toEqual({ screen: 'forge', params: {} })
    expect(parseHash('#/nope?x=1')).toEqual({ screen: 'forge', params: { x: '1' } })
  })

  it('round-trips params, dropping empty values', () => {
    const hash = buildHash('forge', { q: 'wombo combo', element: 'cryo', limit: null, unowned: true, off: false })
    expect(hash).toBe('#/forge?q=wombo+combo&element=cryo&unowned=1')
    expect(parseHash(hash).params).toEqual({ q: 'wombo combo', element: 'cryo', unowned: '1' })
  })

  it('keeps serial characters intact', () => {
    const serial = '@Uge(J0FnkbUI5tpDRG}7is757fxX?}1Kh#K6KUAgOp#Gpzp-!Q8q0%7$'
    expect(parseHash(buildHash('workbench', { serial })).params.serial).toBe(serial)
  })
})
