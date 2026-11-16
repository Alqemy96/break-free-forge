/**
 * Keyboard plumbing: screens register what "run" (Ctrl+Enter) and "focus search" (/) mean for
 * them, and overlays push an Escape handler. The App owns the single keydown listener.
 */
import { useEffect, useRef } from 'react'

export type ActionName = 'run' | 'focusSearch' | 'build'

const actions = new Map<ActionName, () => void>()
const escapeStack: { id: number; fn: () => void }[] = []
let escSeq = 0

export function runAction(name: ActionName): boolean {
  const fn = actions.get(name)
  if (!fn) return false
  fn()
  return true
}

export function hasAction(name: ActionName): boolean {
  return actions.has(name)
}

/** Register a handler for as long as the component is mounted (latest closure always used). */
export function useAction(name: ActionName, fn: () => void, enabled = true): void {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    if (!enabled) return
    const handler = () => ref.current()
    actions.set(name, handler)
    return () => {
      if (actions.get(name) === handler) actions.delete(name)
    }
  }, [name, enabled])
}

/** The most recently opened overlay closes first. Returns true when something handled Escape. */
export function runEscape(): boolean {
  const top = escapeStack[escapeStack.length - 1]
  if (!top) return false
  top.fn()
  return true
}

/** true while a dialog/drawer that owns Escape is open (single-key shortcuts pause then) */
export function overlayOpen(): boolean {
  return escapeStack.length > 0
}

export function useEscape(active: boolean, fn: () => void): void {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    if (!active) return
    const id = ++escSeq
    escapeStack.push({ id, fn: () => ref.current() })
    return () => {
      const at = escapeStack.findIndex((e) => e.id === id)
      if (at >= 0) escapeStack.splice(at, 1)
    }
  }, [active])
}

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tag = target.tagName
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (tag === 'INPUT') {
    const type = (target as HTMLInputElement).type
    return !['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color'].includes(type)
  }
  return false
}
