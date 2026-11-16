import { Check, Copy } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { copyText } from '@/lib/clipboard'
import { cn } from '@/lib/utils'
import { toast } from '@/state/toast'

/**
 * Copy with micro-feedback: the icon morphs into a check, a hazard ring pulses out, the label
 * flips to "Copied". The result is announced through the toast live region.
 */
export function CopyButton({
  text,
  label = 'Copy',
  what = 'Code',
  compact = false,
  className,
  variant = 'secondary',
  disabled = false,
}: {
  text: string
  label?: string
  /** for the announcement: "Code copied" */
  what?: string
  compact?: boolean
  className?: string
  variant?: 'secondary' | 'primary' | 'ghost'
  disabled?: boolean
}) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  const timer = useRef<number>(0)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  const onClick = async () => {
    const ok = await copyText(text)
    setState(ok ? 'copied' : 'failed')
    toast(ok ? `${what} copied` : `Could not copy ${what.toLowerCase()}`, ok ? 'ok' : 'error', ok ? undefined : 'Select the text and copy it by hand.')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setState('idle'), 1500)
  }

  const copied = state === 'copied'
  const tone =
    variant === 'primary'
      ? 'bg-hazard text-hazard-ink hover:bg-hazard-hi border-hazard'
      : variant === 'ghost'
        ? 'border-transparent bg-transparent text-fg-muted hover:text-fg hover:bg-surface-3'
        : 'border-line-strong bg-surface-3 text-fg hover:border-fg-dim hover:bg-surface-4'

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={compact ? `${label} ${what.toLowerCase()}` : undefined}
      className={cn(
        'relative inline-flex select-none items-center justify-center gap-1.5 overflow-visible rounded-[3px] border font-display font-semibold uppercase tracking-[0.06em] transition-colors duration-150 disabled:pointer-events-none disabled:opacity-40',
        compact ? 'size-8' : 'h-8 px-3 text-[13px]',
        tone,
        copied && variant !== 'primary' && 'border-ok/70 text-ok',
        className,
      )}
    >
      <span className="relative grid size-4 place-items-center">
        <AnimatePresence initial={false} mode="popLayout">
          {copied ? (
            <motion.span
              key="check"
              initial={{ scale: 0.3, rotate: -90, opacity: 0 }}
              animate={{ scale: 1, rotate: 0, opacity: 1 }}
              exit={{ scale: 0.3, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 600, damping: 22 }}
              className="grid place-items-center"
            >
              <Check className="size-4" strokeWidth={3} />
            </motion.span>
          ) : (
            <motion.span
              key="copy"
              initial={{ scale: 0.3, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.3, opacity: 0 }}
              transition={{ duration: 0.12 }}
              className="grid place-items-center"
            >
              <Copy className="size-4" />
            </motion.span>
          )}
        </AnimatePresence>
      </span>
      {compact ? null : <span>{copied ? 'Copied' : label}</span>}
      <AnimatePresence>
        {copied ? (
          <motion.span
            key="ring"
            aria-hidden
            initial={{ opacity: 0.7, scale: 0.85 }}
            animate={{ opacity: 0, scale: 1.45 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.55, ease: 'easeOut' }}
            className="pointer-events-none absolute inset-0 rounded-[3px] border-2 border-hazard"
          />
        ) : null}
      </AnimatePresence>
    </button>
  )
}
