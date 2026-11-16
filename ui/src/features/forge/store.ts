/** Forge screen state lives outside the component so results survive screen switches. */
import { create } from 'zustand'
import { api, isApiError } from '@/api'
import type { SearchResponse } from '@/api/types'
import { useApp } from '@/state/app'
import { defaultForm, toSearchParams, type SearchForm } from './form'

export type SearchStatus = 'idle' | 'loading' | 'ok' | 'error'

interface ForgeStore {
  form: SearchForm
  /** the form as it was when the shown results were fetched */
  ran: SearchForm | null
  status: SearchStatus
  data: SearchResponse | null
  error: { code: string; message: string } | null
  runId: number
  setForm: (patch: Partial<SearchForm>) => void
  replaceForm: (form: SearchForm) => void
  run: () => Promise<void>
}

let controller: AbortController | null = null

export const useForge = create<ForgeStore>((set, get) => ({
  form: defaultForm(null),
  ran: null,
  status: 'idle',
  data: null,
  error: null,
  runId: 0,
  setForm: (patch) => set({ form: { ...get().form, ...patch } }),
  replaceForm: (form) => set({ form }),
  async run() {
    controller?.abort()
    const mine = new AbortController()
    controller = mine
    const form = get().form
    set({ status: 'loading', error: null })
    try {
      const data = await api.search(toSearchParams(form), { signal: mine.signal })
      if (controller !== mine) return
      set({ status: 'ok', data, ran: form, runId: get().runId + 1 })
      useApp.getState().reportOk()
    } catch (err) {
      if (controller !== mine) return
      if (isApiError(err) && err.code === 'aborted') return
      useApp.getState().reportError(err)
      set({
        status: 'error',
        error: isApiError(err) ? { code: err.code, message: err.message } : { code: 'internal', message: String(err) },
        ran: form,
      })
    }
  },
}))
