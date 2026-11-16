/** The API the app talks to: the real server (default) or, in mock mode, in-memory fixtures. */
import { createHttpApi } from './client'
import type { Api } from './types'

export const isMock: boolean = __BL4_MOCK__

const impl: Promise<Api> = __BL4_MOCK__
  ? import('../mock/mockApi').then((m) => m.createMockApi())
  : Promise.resolve(createHttpApi())

export const api: Api = {
  meta: (o) => impl.then((a) => a.meta(o)),
  health: (o) => impl.then((a) => a.health(o)),
  stats: (o) => impl.then((a) => a.stats(o)),
  search: (p, o) => impl.then((a) => a.search(p, o)),
  identify: (b, o) => impl.then((a) => a.identify(b, o)),
  transform: (b, o) => impl.then((a) => a.transform(b, o)),
  diff: (x, y, o) => impl.then((a) => a.diff(x, y, o)),
  build: (b, o) => impl.then((a) => a.build(b, o)),
}

export { ApiError, isApiError } from './client'
export type * from './types'
