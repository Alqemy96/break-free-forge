import { AlertTriangle, Download, FileText, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef } from 'react'
import { CopyButton } from '@/components/fx/copy-button'
import { Button } from '@/components/ui/button'
import { useEscape } from '@/hooks/useActions'
import { useFocusTrap } from '@/hooks/useFocusTrap'
import { downloadText } from '@/lib/download'
import { plural, slugify } from '@/lib/format'
import { codesOf, useBuild } from './buildStore'

/**
 * The rendered sheet in a sandboxed iframe. `allow-scripts` lets the sheet's own copy buttons
 * work; without allow-same-origin the sheet cannot touch this app or its storage.
 */
export function BuildSheet() {
  const open = useBuild((s) => s.sheetOpen)
  const result = useBuild((s) => s.result)
  const close = useBuild((s) => s.closeSheet)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const returnTo = useRef<Element | null>(null)
  const dialogRef = useRef<HTMLDivElement>(null)

  useEscape(open, close)
  useFocusTrap(dialogRef, open)

  useEffect(() => {
    if (open) {
      returnTo.current = document.activeElement
      requestAnimationFrame(() => headingRef.current?.focus())
    } else if (returnTo.current instanceof HTMLElement) {
      returnTo.current.focus()
      returnTo.current = null
    }
  }, [open])

  const lo = result?.loadout
  const file = slugify(lo?.title ?? 'loadout')
  const itemWarnings = lo ? lo.items.flatMap((it) => it.warnings.map((w) => `${it.shown_name}: ${w}`)) : []
  const warnings = lo ? [...lo.warnings, ...itemWarnings] : []

  return (
    <AnimatePresence>
      {open && result && lo ? (
        <motion.div
          key="sheet"
          className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/70 p-3 backdrop-blur-[2px] md:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) close()
          }}
        >
          <motion.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="sheet-title"
            className="panel flex w-full max-w-6xl flex-col overflow-hidden"
            initial={{ y: 24, scale: 0.98 }}
            animate={{ y: 0, scale: 1 }}
            exit={{ y: 12, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 380, damping: 34 }}
          >
            <div aria-hidden className="hazard-stripes h-1 w-full" />
            <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="micro text-fg-dim">Code sheet</p>
                <h2 id="sheet-title" ref={headingRef} tabIndex={-1} className="title-display truncate text-[26px] text-fg outline-none">
                  {lo.title}
                </h2>
                <p className="text-[13px] text-fg-muted">
                  {plural(lo.items.length, 'code')}
                  {lo.level !== null ? `, re-leveled to ${lo.level}` : ', stored levels'}
                  {lo.unmatched.length ? `, ${lo.unmatched.length} unmatched` : ''}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <CopyButton text={codesOf(result)} label="Copy all codes" what="All codes" variant="primary" />
                <Button size="sm" variant="secondary" onClick={() => downloadText(`${file}.html`, result.html, 'text/html')}>
                  <Download /> HTML
                </Button>
                <Button size="sm" variant="secondary" onClick={() => downloadText(`${file}.txt`, result.text, 'text/plain')}>
                  <FileText /> Text
                </Button>
                <Button size="icon-sm" variant="ghost" aria-label="Close the sheet (Esc)" onClick={close}>
                  <X />
                </Button>
              </div>
            </div>
            {lo.unmatched.length || warnings.length ? (
              <div className="flex max-h-32 flex-col gap-1 overflow-y-auto border-b border-line bg-warn/[0.05] px-4 py-2 text-[13px]">
                {lo.unmatched.map((u) => (
                  <p key={`u-${u}`} className="flex gap-1.5 text-danger">
                    <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden /> Unmatched: {u}
                  </p>
                ))}
                {warnings.map((w) => (
                  <p key={`w-${w}`} className="flex gap-1.5 text-warn">
                    <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {w}
                  </p>
                ))}
              </div>
            ) : null}
            <iframe
              title={`Code sheet: ${lo.title}`}
              srcDoc={result.html}
              sandbox="allow-scripts"
              allow="clipboard-write"
              referrerPolicy="no-referrer"
              className="min-h-0 w-full flex-1 border-0 bg-white"
            />
            {/* focus guard: tabbing out of the sheet document wraps back to the toolbar */}
            <span tabIndex={0} aria-hidden="true" className="sr-only" onFocus={() => dialogRef.current?.querySelector('button')?.focus()} />
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}
