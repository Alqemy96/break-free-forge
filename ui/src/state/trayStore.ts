/** The tray reducer behind a zustand store, persisted to localStorage (failures are ignored). */
import { create } from 'zustand'
import { readJson, writeJson } from '@/lib/storage'
import { initialTray, parseTrayState, trayReducer, type TrayAction, type TrayState } from './tray'

const KEY = 'bl4forge.tray.v1'

const stored = parseTrayState(readJson(KEY))

interface TrayStore {
  tray: TrayState
  /** true when nothing was restored: the first meta load may set the default level */
  fresh: boolean
  dispatch: (action: TrayAction) => void
}

export const useTray = create<TrayStore>((set) => ({
  tray: stored ?? initialTray(null),
  fresh: stored === null,
  dispatch: (action) => set((s) => ({ tray: trayReducer(s.tray, action), fresh: false })),
}))

useTray.subscribe((s, prev) => {
  if (s.tray !== prev.tray) writeJson(KEY, s.tray)
})

/** First run: default the build level to the server's configured level. */
export function seedTrayLevel(level: number): void {
  const { fresh, tray, dispatch } = useTray.getState()
  if (fresh && tray.level === null) dispatch({ type: 'setLevel', level })
}
