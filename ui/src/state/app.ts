/** App-wide state: server meta, module health, the degraded-module banner, tray visibility. */
import { create } from 'zustand'
import { api, ApiError, isApiError } from '@/api'
import type { Health, Meta, ModuleRow } from '@/api/types'
import { readJson, writeJson } from '@/lib/storage'

export interface Unavailable {
  code: string
  module: string | null
  message: string
  at: number
}

interface AppState {
  meta: Meta | null
  metaError: ApiError | null
  health: Health | null
  healthError: ApiError | null
  healthLoading: boolean
  healthAt: number | null
  /** last 503 module_unavailable / data_missing seen on any call */
  unavailable: Unavailable | null
  /** the server could not be reached at all */
  offline: boolean
  trayOpen: boolean
  loadMeta: () => Promise<void>
  refreshHealth: () => Promise<void>
  /** every screen funnels API errors here so 503s and outages surface app-wide */
  reportError: (err: unknown) => void
  reportOk: () => void
  dismissUnavailable: () => void
  setTrayOpen: (open: boolean) => void
}

const TRAY_OPEN_KEY = 'bl4forge.trayOpen'

export const useApp = create<AppState>((set, get) => ({
  meta: null,
  metaError: null,
  health: null,
  healthError: null,
  healthLoading: false,
  healthAt: null,
  unavailable: null,
  offline: false,
  trayOpen: readJson(TRAY_OPEN_KEY) === true,

  async loadMeta() {
    try {
      const meta = await api.meta()
      set({ meta, metaError: null, offline: false })
    } catch (err) {
      const e = isApiError(err) ? err : new ApiError('network', String(err))
      set({ metaError: e })
      get().reportError(e)
    }
  },

  async refreshHealth() {
    if (get().healthLoading) return
    set({ healthLoading: true })
    try {
      const health = await api.health()
      set({ health, healthError: null, healthLoading: false, healthAt: Date.now(), offline: false })
    } catch (err) {
      const e = isApiError(err) ? err : new ApiError('network', String(err))
      set({ healthError: e, healthLoading: false, healthAt: Date.now() })
      if (e.code === 'network') set({ offline: true })
    }
  },

  reportError(err) {
    if (!isApiError(err)) return
    if (err.code === 'network') {
      set({ offline: true })
      return
    }
    if (err.isUnavailable) {
      set({ unavailable: { code: err.code, module: err.module, message: err.message, at: Date.now() } })
      void get().refreshHealth()
    }
  },

  reportOk() {
    if (get().offline) set({ offline: false })
  },

  dismissUnavailable() {
    set({ unavailable: null })
  },

  setTrayOpen(open) {
    writeJson(TRAY_OPEN_KEY, open)
    set({ trayOpen: open })
  },
}))

/** Modules that are not OK (or have contract problems), worst first. */
export function sickModules(health: Health | null): ModuleRow[] {
  if (!health) return []
  const rank = { failed: 0, blocked: 1, degraded: 2, ok: 3 } as const
  return health.modules
    .filter((m) => m.state !== 'ok' || m.contract_problems.length > 0)
    .sort((a, b) => rank[a.state] - rank[b.state])
}

export type OverallStatus = 'ok' | 'degraded' | 'down' | 'unknown'

export function overallStatus(health: Health | null, offline: boolean): OverallStatus {
  if (offline) return 'down'
  if (!health) return 'unknown'
  const sick = sickModules(health)
  if (sick.length === 0) return 'ok'
  return sick.some((m) => m.state === 'failed' || m.state === 'blocked') ? 'down' : 'degraded'
}
