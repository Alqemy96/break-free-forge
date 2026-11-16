import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function Switch({
  checked,
  onCheckedChange,
  id,
  label,
  description,
  className,
  tone = 'hazard',
}: {
  checked: boolean
  onCheckedChange: (value: boolean) => void
  id: string
  label: ReactNode
  description?: ReactNode
  className?: string
  tone?: 'hazard' | 'danger'
}) {
  const on = tone === 'danger' ? 'bg-danger border-danger' : 'bg-hazard border-hazard'
  return (
    <div className={cn('flex items-start gap-3', className)}>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-describedby={description ? `${id}-desc` : undefined}
        onClick={() => onCheckedChange(!checked)}
        className={cn(
          'relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full border p-0.5 transition-colors duration-150',
          checked ? on : 'border-line-strong bg-surface-3',
        )}
      >
        <motion.span
          layout
          transition={{ type: 'spring', stiffness: 700, damping: 35 }}
          className={cn('block size-3.5 rounded-full', checked ? 'ml-auto bg-hazard-ink' : 'bg-fg-muted')}
        />
      </button>
      <div className="min-w-0">
        <label htmlFor={id} className="block text-[14px] font-medium leading-tight text-fg">
          {label}
        </label>
        {description ? (
          <p id={`${id}-desc`} className="mt-1 text-[12.5px] leading-snug text-fg-dim">
            {description}
          </p>
        ) : null}
      </div>
    </div>
  )
}
