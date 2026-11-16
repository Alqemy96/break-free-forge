import { useEffect, type RefObject } from 'react'

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), iframe, [tabindex]:not([tabindex="-1"])'

/** Keep Tab / Shift+Tab inside a modal while it is open. */
export function useFocusTrap(ref: RefObject<HTMLElement | null>, active: boolean): void {
  useEffect(() => {
    if (!active) return
    const onKey = (e: KeyboardEvent) => {
      const root = ref.current
      if (e.key !== 'Tab' || !root) return
      // focus guards (aria-hidden sentinels) redirect on their own and are not tab stops here
      const items = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.getAttribute('aria-hidden') !== 'true' && (el.offsetParent !== null || el === document.activeElement),
      )
      const first = items[0]
      const last = items[items.length - 1]
      if (!first || !last) return
      const active = document.activeElement as HTMLElement | null
      const inside = root.contains(active)
      const at = active ? items.indexOf(active) : -1
      if (e.shiftKey && (!inside || at <= 0)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && (!inside || at === items.length - 1)) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [ref, active])
}
