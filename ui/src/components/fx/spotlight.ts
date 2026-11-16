import type { PointerEvent } from 'react'

/** Spotlight / border-glow cards: write the pointer position into CSS vars (no re-render). */
export function trackSpotlight(e: PointerEvent<HTMLElement>): void {
  const el = e.currentTarget
  const r = el.getBoundingClientRect()
  el.style.setProperty('--mx', `${e.clientX - r.left}px`)
  el.style.setProperty('--my', `${e.clientY - r.top}px`)
}
