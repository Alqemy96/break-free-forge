import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { cn } from '@/lib/utils'
import { useToasts, type ToastTone } from '@/state/toast'

const ICON = { ok: CheckCircle2, info: Info, warn: AlertTriangle, error: XCircle } satisfies Record<ToastTone, unknown>
const TONE: Record<ToastTone, string> = {
  ok: 'text-ok',
  info: 'text-violet-hi',
  warn: 'text-warn',
  error: 'text-danger',
}

/** Bottom-left stack; a polite live region (never steals focus). */
export function Toaster() {
  const toasts = useToasts((s) => s.toasts)
  const dismiss = useToasts((s) => s.dismiss)
  return (
    <div aria-live="polite" aria-relevant="additions" className="pointer-events-none fixed bottom-4 left-[92px] z-[60] flex w-[min(360px,calc(100vw-110px))] flex-col gap-2">
      <AnimatePresence initial={false}>
        {toasts.map((t) => {
          const Icon = ICON[t.tone]
          return (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, y: 16, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: -20, transition: { duration: 0.15 } }}
              transition={{ type: 'spring', stiffness: 500, damping: 36 }}
              className="pointer-events-auto flex items-start gap-2.5 border border-line-strong bg-surface-4/95 px-3 py-2.5 shadow-[0_14px_40px_-12px_rgb(0_0_0/0.9)]"
              role="status"
              onClick={() => dismiss(t.id)}
            >
              <Icon className={cn('mt-0.5 size-4 shrink-0', TONE[t.tone])} aria-hidden />
              <div className="min-w-0">
                <p className="text-[13.5px] font-medium text-fg">{t.title}</p>
                {t.detail ? <p className="text-[12.5px] text-fg-muted">{t.detail}</p> : null}
              </div>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
