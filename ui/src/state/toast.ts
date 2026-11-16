/** Tiny toast queue (announced through an aria-live region, never steals focus). */
import { create } from 'zustand'

export type ToastTone = 'ok' | 'info' | 'warn' | 'error'

export interface Toast {
  id: number
  title: string
  detail?: string
  tone: ToastTone
}

interface ToastStore {
  toasts: Toast[]
  push: (title: string, tone?: ToastTone, detail?: string) => void
  dismiss: (id: number) => void
}

let seq = 0

export const useToasts = create<ToastStore>((set, get) => ({
  toasts: [],
  push(title, tone = 'info', detail) {
    const id = ++seq
    const toast: Toast = detail === undefined ? { id, title, tone } : { id, title, tone, detail }
    set({ toasts: [...get().toasts.slice(-3), toast] })
    window.setTimeout(() => get().dismiss(id), tone === 'error' ? 6000 : 3200)
  },
  dismiss(id) {
    set({ toasts: get().toasts.filter((t) => t.id !== id) })
  },
}))

export const toast = (title: string, tone?: ToastTone, detail?: string) => useToasts.getState().push(title, tone, detail)
