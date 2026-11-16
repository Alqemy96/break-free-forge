/**
 * A small typed fetch client for the forge server. Every failure becomes an `ApiError` carrying the
 * contract's `{error: {code, message}}`, or a client-side code when the server never answered.
 */
import {
  ERROR_CODES,
  type Api,
  type BuildRequest,
  type BuildResponse,
  type DiffResponse,
  type ErrorCode,
  type Health,
  type IdentifyRequest,
  type IdentifyResponse,
  type Meta,
  type RequestOptions,
  type SearchParams,
  type SearchResponse,
  type Stats,
  type TransformRequest,
  type TransformResponse,
} from './types'

/** Contract codes plus the ones only the client can observe. */
export type ClientErrorCode = ErrorCode | 'network' | 'aborted' | 'bad_response'

export const MODULE_NAMES = ['codec', 'data', 'rules', 'ops', 'catalog', 'builder', 'render'] as const
export type ModuleName = (typeof MODULE_NAMES)[number]

export class ApiError extends Error {
  readonly code: ClientErrorCode
  /** HTTP status, 0 when there was no response */
  readonly status: number
  /** the module named in a 503 message, when one can be read from it */
  readonly module: ModuleName | null

  constructor(code: ClientErrorCode, message: string, status = 0, module: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    const named = module && (MODULE_NAMES as readonly string[]).includes(module) ? (module as ModuleName) : null
    this.module = code === 'module_unavailable' || code === 'data_missing' ? (named ?? moduleFromMessage(message)) : null
  }

  /** a module or its data is missing: the UI shows the degraded-module banner */
  get isUnavailable(): boolean {
    return this.code === 'module_unavailable' || this.code === 'data_missing'
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError
}

const UNREACHABLE =
  'Cannot reach the forge server. Start it with `bl4forge serve` (it listens on 127.0.0.1:8734), then retry.'

/** Find the module a server message talks about: a quoted name wins, then the first bare word. */
export function moduleFromMessage(message: string): ModuleName | null {
  const lower = message.toLowerCase()
  for (const name of MODULE_NAMES) {
    if (lower.includes(`'${name}'`) || lower.includes(`"${name}"`)) return name
  }
  let best: { name: ModuleName; at: number } | null = null
  for (const name of MODULE_NAMES) {
    const match = new RegExp(`\\b${name}\\b`).exec(lower)
    if (match && (best === null || match.index < best.at)) best = { name, at: match.index }
  }
  return best ? best.name : null
}

function isErrorCode(value: unknown): value is ErrorCode {
  return typeof value === 'string' && (ERROR_CODES as readonly string[]).includes(value)
}

const STATUS_FALLBACK: Record<number, [ErrorCode, string]> = {
  400: ['bad_request', 'The server rejected the request.'],
  404: ['not_found', 'Not found.'],
  405: ['bad_request', 'Method not allowed.'],
  413: ['bad_request', 'Request too large (the server accepts at most 1 MB).'],
  415: ['bad_request', 'The server only accepts application/json bodies.'],
  500: ['internal', 'The forge server hit an internal error.'],
  503: ['module_unavailable', 'A module the forge needs is unavailable.'],
}

/** Map a non-2xx response (status + raw body text) to an ApiError. Pure: unit-tested. */
export function errorFromResponse(status: number, bodyText: string): ApiError {
  let parsed: unknown = null
  try {
    parsed = bodyText ? JSON.parse(bodyText) : null
  } catch {
    parsed = null
  }
  if (parsed && typeof parsed === 'object' && 'error' in parsed) {
    const err = (parsed as { error: unknown }).error
    if (err && typeof err === 'object') {
      const code = (err as { code?: unknown }).code
      const message = (err as { message?: unknown }).message
      const module = (err as { module?: unknown }).module
      const text = typeof message === 'string' && message.trim() ? message : fallbackMessage(status)
      return new ApiError(isErrorCode(code) ? code : codeForStatus(status), text, status, typeof module === 'string' ? module : null)
    }
  }
  // No contract body. A 5xx without JSON almost always means nothing is listening behind the
  // dev proxy (or a different program answered): say so instead of a bare status code.
  if (status >= 500 && parsed === null) return new ApiError('network', UNREACHABLE, status)
  return new ApiError(codeForStatus(status), fallbackMessage(status), status)
}

function codeForStatus(status: number): ErrorCode {
  return STATUS_FALLBACK[status]?.[0] ?? (status >= 500 ? 'internal' : 'bad_request')
}

function fallbackMessage(status: number): string {
  return STATUS_FALLBACK[status]?.[1] ?? `Unexpected HTTP ${status} from the forge server.`
}

/** Map anything thrown by fetch/parsing to an ApiError. Pure: unit-tested. */
export function errorFromThrown(err: unknown): ApiError {
  if (err instanceof ApiError) return err
  if (err && typeof err === 'object' && (err as { name?: unknown }).name === 'AbortError') {
    return new ApiError('aborted', 'Request cancelled.')
  }
  return new ApiError('network', UNREACHABLE)
}

/** Query string for /api/search: drops empty values, booleans become 1/0. Pure: unit-tested. */
export function searchQueryString(params: SearchParams): string {
  const qs = new URLSearchParams()
  const put = (key: string, value: string | number | boolean | undefined | null) => {
    if (value === undefined || value === null) return
    if (typeof value === 'boolean') qs.set(key, value ? '1' : '0')
    else if (typeof value === 'number') {
      if (Number.isFinite(value)) qs.set(key, String(Math.trunc(value)))
    } else if (value.trim()) qs.set(key, value.trim())
  }
  put('query', params.query)
  put('type', params.type)
  put('element', params.element)
  put('manufacturer', params.manufacturer)
  put('rarity', params.rarity)
  put('character', params.character)
  put('limit', params.limit)
  put('include_unowned', params.include_unowned)
  put('verify_element', params.verify_element)
  put('level', params.level)
  const text = qs.toString()
  return text ? `?${text}` : ''
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>

export function createHttpApi(fetchImpl: FetchLike = (input, init) => fetch(input, init), base = '/api'): Api {
  async function call<T>(path: string, init: RequestInit & RequestOptions = {}): Promise<T> {
    let response: Response
    try {
      response = await fetchImpl(base + path, {
        ...init,
        headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}) },
        credentials: 'same-origin',
        cache: 'no-store',
      })
    } catch (err) {
      throw errorFromThrown(err)
    }
    let text: string
    try {
      text = await response.text()
    } catch (err) {
      throw errorFromThrown(err)
    }
    if (!response.ok) throw errorFromResponse(response.status, text)
    try {
      return JSON.parse(text) as T
    } catch {
      const type = response.headers.get('content-type') ?? 'unknown content'
      throw new ApiError('bad_response', `Expected JSON from ${base}${path}, got ${type}.`, response.status)
    }
  }

  const post = <T>(path: string, body: unknown, opts?: RequestOptions) =>
    call<T>(path, { method: 'POST', body: JSON.stringify(body), signal: opts?.signal })

  return {
    meta: (opts) => call<Meta>('/meta', { signal: opts?.signal }),
    health: (opts) => call<Health>('/health', { signal: opts?.signal }),
    stats: (opts) => call<Stats>('/stats', { signal: opts?.signal }),
    search: (params, opts) => call<SearchResponse>(`/search${searchQueryString(params)}`, { signal: opts?.signal }),
    identify: (body: IdentifyRequest, opts) => post<IdentifyResponse>('/identify', body, opts),
    transform: (body: TransformRequest, opts) => post<TransformResponse>('/transform', body, opts),
    diff: (a, b, opts) => post<DiffResponse>('/diff', { a, b }, opts),
    build: (body: BuildRequest, opts) => post<BuildResponse>('/build', body, opts),
  }
}
