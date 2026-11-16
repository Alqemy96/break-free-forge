/** Hash routing: '#/forge?query=anarchy&element=cryo'. Pure helpers, unit-tested. */

export const SCREENS = ['forge', 'workbench', 'health'] as const
export type Screen = (typeof SCREENS)[number]

export interface Route {
  screen: Screen
  params: Record<string, string>
}

export function parseHash(hash: string): Route {
  const body = hash.replace(/^#/, '').replace(/^\//, '')
  const qIndex = body.indexOf('?')
  const path = (qIndex >= 0 ? body.slice(0, qIndex) : body).replace(/\/+$/, '').toLowerCase()
  const query = qIndex >= 0 ? body.slice(qIndex + 1) : ''
  const screen = (SCREENS as readonly string[]).includes(path) ? (path as Screen) : 'forge'
  const params: Record<string, string> = {}
  for (const [k, v] of new URLSearchParams(query)) {
    if (v !== '') params[k] = v
  }
  return { screen, params }
}

export function buildHash(screen: Screen, params: Record<string, string | number | boolean | null | undefined> = {}): string {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '' || v === false) continue
    qs.set(k, v === true ? '1' : String(v))
  }
  const text = qs.toString()
  return `#/${screen}${text ? `?${text}` : ''}`
}
