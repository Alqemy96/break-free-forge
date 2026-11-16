import { describe, expect, it } from 'vitest'
import { parseSpec } from './spec'

describe('parseSpec', () => {
  it('accepts the legacy spec, mapping label_name to display_name', () => {
    const r = parseSpec('[{"group":"Weapons","query":"wombo combo","element":"cryo","label_name":"Wombo"},{"type":"repkit","count":2}]')
    expect(r).toEqual({
      ok: true,
      notes: [],
      requests: [
        { group: 'Weapons', query: 'wombo combo', element: 'cryo', display_name: 'Wombo' },
        { type: 'repkit', count: 2 },
      ],
    })
  })

  it('accepts {"requests": [...]} and reports unknown keys', () => {
    const r = parseSpec('{"requests":[{"serial":"@Uabc","colour":"red"}]}')
    expect(r.ok && r.notes).toEqual(['entry 1: ignoring unknown key(s) colour'])
  })

  it('rejects bad input with a readable reason', () => {
    expect(parseSpec('')).toMatchObject({ ok: false })
    expect(parseSpec('{')).toMatchObject({ ok: false, error: expect.stringMatching(/^Not valid JSON/) })
    expect(parseSpec('[]')).toMatchObject({ ok: false, error: expect.stringMatching(/empty/) })
    expect(parseSpec('[1]')).toMatchObject({ ok: false, error: 'entry 1 must be a JSON object.' })
    expect(parseSpec('[{"query":5}]')).toMatchObject({ ok: false, error: 'entry 1: "query" must be a string.' })
    expect(parseSpec('[{"count":0}]')).toMatchObject({ ok: false })
    expect(parseSpec('[{"serial":" @Uabc"}]')).toMatchObject({ ok: false })
  })
})
