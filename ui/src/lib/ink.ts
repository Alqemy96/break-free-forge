/**
 * Brush-ink borders use an SVG displacement filter. On a slow GPU/CPU that can cost frames, so the
 * app falls back to plain borders ("ink-lite") when:
 *  - the URL has ?ink=lite (force on) / ?ink=full (force off), or
 *  - localStorage "bf-ink" is "lite", or
 *  - a short frame-time probe after load averages above INK_SLOW_MS per frame.
 * Pure helpers are exported for the unit test; the DOM wiring is in probeInkMode().
 */
export const INK_SLOW_MS = 28
export const INK_CLASS = 'ink-lite'

export type InkMode = 'lite' | 'full' | 'auto'

export function inkModeFrom(search: string, stored: string | null): InkMode {
  const q = new URLSearchParams(search).get('ink')
  if (q === 'lite' || q === 'full') return q
  if (stored === 'lite') return 'lite'
  return 'auto'
}

export function isSlow(frameTimesMs: number[], limit = INK_SLOW_MS): boolean {
  if (frameTimesMs.length === 0) return false
  const avg = frameTimesMs.reduce((a, b) => a + b, 0) / frameTimesMs.length
  return avg > limit
}

export function probeInkMode(): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  let stored: string | null = null
  try {
    stored = window.localStorage.getItem('bf-ink')
  } catch {
    stored = null
  }
  const mode = inkModeFrom(window.location.search, stored)
  if (mode === 'lite') {
    root.classList.add(INK_CLASS)
    return
  }
  if (mode === 'full') return
  const times: number[] = []
  let last = 0
  const tick = (t: number) => {
    if (last) times.push(t - last)
    last = t
    if (times.length < 30) {
      requestAnimationFrame(tick)
      return
    }
    // the first frames include font/layout work, so judge the settled tail only
    if (isSlow(times.slice(10))) {
      root.classList.add(INK_CLASS)
      try {
        window.localStorage.setItem('bf-ink', 'lite')
      } catch {
        /* ignore */
      }
    }
  }
  window.setTimeout(() => requestAnimationFrame(tick), 800)
}
