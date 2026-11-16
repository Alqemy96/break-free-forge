import { describe, expect, it } from 'vitest'
import { defaultForm, formFromHash, formToHash, hashHasSearch, toSearchParams } from './form'

describe('forge form', () => {
  it('maps the form to /api/search params', () => {
    const form = { ...defaultForm(60), query: ' anarchy ', element: 'Electric', type: 'shotgun', includeUnowned: true, verifyElement: false, limit: 999 }
    expect(toSearchParams(form)).toEqual({
      query: 'anarchy',
      type: 'shotgun',
      element: 'shock',
      level: 60,
      limit: 200,
      include_unowned: true,
      verify_element: false,
    })
  })

  it('omits level when stored levels are kept', () => {
    expect(toSearchParams(defaultForm(null))).toEqual({ limit: 25 })
  })

  it('round-trips through the hash', () => {
    const form = { ...defaultForm(60), query: 'wombo', element: 'cryo', character: 'gravitar', level: null, limit: 50 }
    const hash = Object.fromEntries(
      Object.entries(formToHash(form))
        .filter(([, v]) => v !== null)
        .map(([k, v]) => [k, v === true ? '1' : String(v)]),
    )
    expect(formFromHash(hash, 60)).toEqual(form)
    expect(hashHasSearch(hash)).toBe(true)
    expect(hashHasSearch({ level: '60' })).toBe(false)
  })

  it('uses the fallback level when the hash has none', () => {
    expect(formFromHash({ q: 'x' }, 55).level).toBe(55)
  })
})
