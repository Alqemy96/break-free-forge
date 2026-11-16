/** One build at a time (tray or quick build); the sheet viewer reads the last result. */
import { create } from 'zustand'
import { api, isApiError } from '@/api'
import type { BuildRequest, BuildResponse } from '@/api/types'
import { useApp } from '@/state/app'

export type BuildSource = 'tray' | 'quick'

interface BuildStore {
  status: 'idle' | 'loading' | 'ok' | 'error'
  source: BuildSource | null
  result: BuildResponse | null
  error: { code: string; message: string } | null
  sheetOpen: boolean
  build: (body: BuildRequest, source: BuildSource) => Promise<BuildResponse | null>
  openSheet: () => void
  closeSheet: () => void
}

export const useBuild = create<BuildStore>((set) => ({
  status: 'idle',
  source: null,
  result: null,
  error: null,
  sheetOpen: false,
  async build(body, source) {
    set({ status: 'loading', source, error: null })
    try {
      const result = await api.build(body)
      set({ status: 'ok', result, sheetOpen: result.loadout.items.length > 0 && source === 'tray' })
      useApp.getState().reportOk()
      return result
    } catch (err) {
      useApp.getState().reportError(err)
      set({
        status: 'error',
        error: isApiError(err) ? { code: err.code, message: err.message } : { code: 'internal', message: String(err) },
      })
      return null
    }
  },
  openSheet: () => set({ sheetOpen: true }),
  closeSheet: () => set({ sheetOpen: false }),
}))

/** Every code in a built loadout, one per line (sheet order). */
export function codesOf(result: BuildResponse): string {
  return result.loadout.items.map((it) => it.serial).join('\n')
}
