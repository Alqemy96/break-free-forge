import { AnimatePresence, motion } from 'motion/react'
import { useId, useState, type ReactElement, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * Hover/focus tooltip. The trigger keeps its own semantics; the bubble is linked with
 * aria-describedby, so it is announced and works from the keyboard too.
 */
export function Tooltip({
  content,
  children,
  side = 'bottom',
  className,
}: {
  content: ReactNode
  children: (props: { 'aria-describedby': string | undefined }) => ReactElement
  side?: 'top' | 'bottom' | 'left'
  className?: string
}) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const pos =
    side === 'top'
      ? 'bottom-full left-1/2 mb-2 -translate-x-1/2'
      : side === 'left'
        ? 'right-full top-1/2 mr-2 -translate-y-1/2'
        : 'top-full right-0 mt-2'
  return (
    <span
      className="relative inline-flex"
      onPointerEnter={() => setOpen(true)}
      onPointerLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children({ 'aria-describedby': open ? id : undefined })}
      <AnimatePresence>
        {open ? (
          <motion.span
            id={id}
            role="tooltip"
            initial={{ opacity: 0, y: side === 'top' ? 4 : -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
            className={cn(
              'pointer-events-none absolute z-50 w-max max-w-[320px] rounded-[3px] border border-line-strong bg-surface-4 px-3 py-2 text-left text-[12.5px] leading-snug text-fg shadow-[0_12px_30px_-10px_rgb(0_0_0/0.9)]',
              pos,
              className,
            )}
          >
            {content}
          </motion.span>
        ) : null}
      </AnimatePresence>
    </span>
  )
}
