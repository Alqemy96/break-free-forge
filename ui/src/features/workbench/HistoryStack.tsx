import { History, Undo2 } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { SerialText } from '@/components/item/serial'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useWorkbench } from './store'

/** The serial's history: every accepted change stacks on top; Undo steps back one. */
export function HistoryStack() {
  const stack = useWorkbench((s) => s.wb.stack)
  const dispatch = useWorkbench((s) => s.dispatch)
  return (
    <section className="panel p-4" aria-labelledby="history-h">
      <div className="mb-3 flex items-center justify-between">
        <h3 id="history-h" className="micro flex items-center gap-1.5 text-fg-muted">
          <History className="size-3.5 text-hazard" aria-hidden /> History ({stack.length})
        </h3>
        <Button size="sm" variant="ghost" disabled={stack.length <= 1} onClick={() => dispatch({ type: 'undo' })}>
          <Undo2 /> Undo
        </Button>
      </div>
      <ol className="flex flex-col-reverse gap-1.5">
        <AnimatePresence initial={false}>
          {stack.map((entry, i) => {
            const current = i === stack.length - 1
            return (
              <motion.li
                key={`${i}-${entry.payload.serial}`}
                layout
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 8 }}
                className={cn(
                  'flex items-center gap-2.5 border px-2.5 py-1.5',
                  current ? 'border-hazard/50 bg-hazard/[0.06]' : 'border-line bg-surface-2/50 opacity-80',
                )}
                aria-current={current ? 'step' : undefined}
              >
                <span className={cn('font-mono text-[11px]', current ? 'text-hazard-hi' : 'text-fg-dim')}>{String(i + 1).padStart(2, '0')}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] text-fg">{entry.label}</span>
                  <SerialText serial={entry.payload.serial} className="block truncate text-[11.5px]" />
                </span>
                {current ? <span className="micro text-[10px] text-hazard-hi">current</span> : null}
              </motion.li>
            )
          })}
        </AnimatePresence>
      </ol>
    </section>
  )
}
