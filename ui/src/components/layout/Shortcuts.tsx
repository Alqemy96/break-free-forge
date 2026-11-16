import { X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/misc'
import { useEscape } from '@/hooks/useActions'
import { useFocusTrap } from '@/hooks/useFocusTrap'

const ROWS: [string[], string][] = [
  [['/'], 'Focus search (forge) or the serial box (bench)'],
  [['Ctrl', 'Enter'], 'Run: search, identify, refresh health; build when focus is in the tray'],
  [['Esc'], 'Close the open sheet, drawer or dialog'],
  [['L'], 'Open or close the loadout tray'],
  [['1'], 'Forge'],
  [['2'], 'Workbench'],
  [['3'], 'Health'],
  [['?'], 'This list'],
]

export function Shortcuts({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useEscape(open, onClose)
  useFocusTrap(ref, open)
  useEffect(() => {
    if (open) ref.current?.focus()
  }, [open])
  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={(e) => e.target === e.currentTarget && onClose()}
        >
          <motion.div
            ref={ref}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-labelledby="keys-h"
            initial={{ y: 12, scale: 0.98 }}
            animate={{ y: 0, scale: 1 }}
            className="panel w-full max-w-md p-5 outline-none"
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 id="keys-h" className="title-display text-[24px] text-fg">
                Keyboard
              </h2>
              <Button size="icon-sm" variant="ghost" aria-label="Close" onClick={onClose}>
                <X />
              </Button>
            </div>
            <dl className="flex flex-col gap-2">
              {ROWS.map(([keys, what]) => (
                <div key={what} className="flex items-start justify-between gap-4 border-b border-line/60 pb-2 last:border-b-0">
                  <dt className="flex shrink-0 items-center gap-1">
                    {keys.map((k, i) => (
                      <span key={k} className="flex items-center gap-1">
                        {i ? <span className="text-fg-dim">+</span> : null}
                        <Kbd>{k}</Kbd>
                      </span>
                    ))}
                  </dt>
                  <dd className="m-0 text-right text-[13.5px] text-fg-muted">{what}</dd>
                </div>
              ))}
            </dl>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}
