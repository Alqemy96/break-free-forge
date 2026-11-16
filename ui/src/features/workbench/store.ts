/** Workbench state (survives screen switches): the history reducer plus its async actions. */
import { create } from 'zustand'
import { api, isApiError } from '@/api'
import type { IdentifyResponse, TransformRequest } from '@/api/types'
import { useApp } from '@/state/app'
import { emptyWorkbench, workbenchReducer, type WorkbenchAction, type WorkbenchState } from '@/state/workbench'

export interface UiError {
  code: string
  message: string
}

function toUiError(err: unknown): UiError {
  return isApiError(err) ? { code: err.code, message: err.message } : { code: 'internal', message: String(err) }
}

interface WorkbenchStore {
  wb: WorkbenchState
  input: string
  identifying: boolean
  identifyError: UiError | null
  /** which action is running: 'relevel' | 'set_element' | ... */
  busy: string | null
  actionError: UiError | null
  source: IdentifyResponse | null
  sourceLoading: boolean
  sourceError: UiError | null
  setInput: (text: string) => void
  dispatch: (action: WorkbenchAction) => void
  identify: (serial: string, level?: number) => Promise<void>
  transform: (req: TransformRequest, label: string) => Promise<void>
  loadSource: (serial: string) => Promise<void>
  clearSource: () => void
}

export const useWorkbench = create<WorkbenchStore>((set, get) => ({
  wb: emptyWorkbench,
  input: '',
  identifying: false,
  identifyError: null,
  busy: null,
  actionError: null,
  source: null,
  sourceLoading: false,
  sourceError: null,

  setInput: (input) => set({ input }),
  dispatch: (action) => set({ wb: workbenchReducer(get().wb, action), actionError: null }),

  async identify(serial, level) {
    const s = serial.trim()
    if (!s) {
      set({ identifyError: { code: 'bad_request', message: 'Paste a serial (it starts with @U) first.' } })
      return
    }
    set({ identifying: true, identifyError: null, input: s })
    try {
      const payload = await api.identify(level === undefined ? { serial: s } : { serial: s, level })
      set({
        wb: workbenchReducer(get().wb, { type: 'loaded', payload, label: level === undefined ? 'identified' : `identified at Lv ${level}` }),
        identifying: false,
        input: payload.serial,
        actionError: null,
      })
      useApp.getState().reportOk()
    } catch (err) {
      useApp.getState().reportError(err)
      set({ identifying: false, identifyError: toUiError(err) })
    }
  },

  async transform(req, label) {
    set({ busy: req.op, actionError: null })
    try {
      const result = await api.transform(req)
      // a random reseed: name the seed the server picked
      const shown = req.op === 'reseed' && req.seed === undefined && result.seed !== undefined ? `reseed ${result.seed} (random)` : label
      set({ wb: workbenchReducer(get().wb, { type: 'proposed', result, label: shown }), busy: null })
      try {
        const diff = await api.diff(result.previous || req.serial, result.serial)
        set({ wb: workbenchReducer(get().wb, { type: 'diffLoaded', serial: result.serial, rows: diff.rows }) })
      } catch (err) {
        useApp.getState().reportError(err)
        set({ wb: workbenchReducer(get().wb, { type: 'diffFailed', serial: result.serial, message: toUiError(err).message }) })
      }
    } catch (err) {
      useApp.getState().reportError(err)
      set({ busy: null, actionError: toUiError(err) })
    }
  },

  async loadSource(serial) {
    const s = serial.trim()
    if (!s) return
    set({ sourceLoading: true, sourceError: null })
    try {
      const source = await api.identify({ serial: s })
      set({ source, sourceLoading: false })
    } catch (err) {
      useApp.getState().reportError(err)
      set({ sourceLoading: false, sourceError: toUiError(err), source: null })
    }
  },

  clearSource: () => set({ source: null, sourceError: null }),
}))
