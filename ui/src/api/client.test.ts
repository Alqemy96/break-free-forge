import { describe, expect, it } from 'vitest'
import { ApiError, createHttpApi, errorFromResponse, errorFromThrown, moduleFromMessage, searchQueryString, type FetchLike } from './client'

const json = (status: number, body: unknown, headers: Record<string, string> = { 'content-type': 'application/json' }) =>
  new Response(typeof body === 'string' ? body : JSON.stringify(body), { status, headers })

describe('errorFromResponse', () => {
  it('maps the contract error body verbatim', () => {
    const e = errorFromResponse(400, JSON.stringify({ error: { code: 'serial_error', message: 'bad serial: truncated' } }))
    expect(e).toBeInstanceOf(ApiError)
    expect(e.code).toBe('serial_error')
    expect(e.message).toBe('bad serial: truncated')
    expect(e.status).toBe(400)
    expect(e.module).toBeNull()
  })

  it('reads the module out of a 503 module_unavailable message', () => {
    const e = errorFromResponse(503, JSON.stringify({ error: { code: 'module_unavailable', message: "module 'catalog' is unavailable (failed)" } }))
    expect(e.code).toBe('module_unavailable')
    expect(e.isUnavailable).toBe(true)
    expect(e.module).toBe('catalog')
  })

  it('prefers the module the server names in error.module', () => {
    const body = { error: { code: 'module_unavailable', message: 'needs catalog which is failed', module: 'builder' } }
    expect(errorFromResponse(503, JSON.stringify(body)).module).toBe('builder')
  })

  it('treats data_missing as unavailable too', () => {
    const e = errorFromResponse(503, JSON.stringify({ error: { code: 'data_missing', message: 'manifest for data is missing' } }))
    expect(e.isUnavailable).toBe(true)
    expect(e.module).toBe('data')
  })

  it('falls back to the status when the code is unknown', () => {
    const e = errorFromResponse(404, JSON.stringify({ error: { code: 'weird', message: 'nope' } }))
    expect(e.code).toBe('not_found')
    expect(e.message).toBe('nope')
  })

  it('uses a status message when the body has no message', () => {
    expect(errorFromResponse(413, JSON.stringify({ error: { code: 'bad_request' } })).message).toMatch(/1 MB/)
    expect(errorFromResponse(415, '').code).toBe('bad_request')
  })

  it('reports an unreachable server for a 5xx without a JSON body (dev proxy, nothing listening)', () => {
    const e = errorFromResponse(500, '')
    expect(e.code).toBe('network')
    expect(e.message).toMatch(/bl4forge serve/)
    expect(errorFromResponse(502, '<html>Bad gateway</html>').code).toBe('network')
  })
})

describe('errorFromThrown', () => {
  it('maps aborts and network failures', () => {
    const abort = Object.assign(new Error('aborted'), { name: 'AbortError' })
    expect(errorFromThrown(abort).code).toBe('aborted')
    expect(errorFromThrown(new TypeError('Failed to fetch')).code).toBe('network')
  })
  it('passes ApiErrors through', () => {
    const e = new ApiError('internal', 'x', 500)
    expect(errorFromThrown(e)).toBe(e)
  })
})

describe('moduleFromMessage', () => {
  it('prefers a quoted module name', () => {
    expect(moduleFromMessage("needs ops which needs 'rules'")).toBe('rules')
  })
  it('takes the first bare module word, whole words only', () => {
    expect(moduleFromMessage('builder is blocked: needs catalog')).toBe('builder')
    expect(moduleFromMessage('the operations failed')).toBeNull()
  })
})

describe('searchQueryString', () => {
  it('drops empty values and encodes booleans as 1/0', () => {
    expect(searchQueryString({ query: ' anarchy ', element: 'cryo', type: '', limit: 25, include_unowned: true, verify_element: false, level: 60 })).toBe(
      '?query=anarchy&element=cryo&limit=25&include_unowned=1&verify_element=0&level=60',
    )
    expect(searchQueryString({})).toBe('')
  })
})

describe('createHttpApi', () => {
  it('GETs same-origin /api paths and parses JSON', async () => {
    const calls: [string, RequestInit | undefined][] = []
    const fetchImpl: FetchLike = async (input, init) => {
      calls.push([input, init])
      return json(200, { count: 0, level: 60, results: [], hidden: [], dropped_element_mismatch: 0 })
    }
    const api = createHttpApi(fetchImpl)
    const res = await api.search({ query: 'x', limit: 3 })
    expect(res.count).toBe(0)
    expect(calls[0]?.[0]).toBe('/api/search?query=x&limit=3')
    expect(calls[0]?.[1]?.method).toBeUndefined()
  })

  it('POSTs JSON bodies with the content type the server requires', async () => {
    let seen: RequestInit | undefined
    const api = createHttpApi(async (_input, init) => {
      seen = init
      return json(200, { rows: [] })
    })
    await api.diff('@Ua', '@Ub')
    expect(seen?.method).toBe('POST')
    expect((seen?.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(seen?.body).toBe(JSON.stringify({ a: '@Ua', b: '@Ub' }))
  })

  it('throws the mapped ApiError on an error status', async () => {
    const api = createHttpApi(async () => json(503, { error: { code: 'module_unavailable', message: "module 'builder' is unavailable" } }))
    await expect(api.build({ requests: [] })).rejects.toMatchObject({ code: 'module_unavailable', status: 503, module: 'builder' })
  })

  it('throws network when fetch itself fails', async () => {
    const api = createHttpApi(async () => {
      throw new TypeError('Failed to fetch')
    })
    await expect(api.meta()).rejects.toMatchObject({ code: 'network', status: 0 })
  })

  it('throws bad_response when a 200 is not JSON (e.g. the SPA fallback answered)', async () => {
    const api = createHttpApi(async () => json(200, '<!doctype html>', { 'content-type': 'text/html' }))
    await expect(api.health()).rejects.toMatchObject({ code: 'bad_response' })
  })
})
