import { motion } from 'motion/react'
import { useRef, type KeyboardEvent, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

export interface TabItem<T extends string> {
  id: T
  label: ReactNode
  icon?: ReactNode
  disabled?: boolean
}

export const tabId = (base: string, id: string) => `${base}-tab-${id}`
export const panelId = (base: string, id: string) => `${base}-panel-${id}`

/** Accessible tabs (arrow keys, Home/End) with a sliding indicator (shared layout animation). */
export function Tabs<T extends string>({
  base,
  value,
  onChange,
  items,
  label,
  className,
}: {
  base: string
  value: T
  onChange: (id: T) => void
  items: TabItem<T>[]
  label: string
  className?: string
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const enabled = items.filter((i) => !i.disabled)
  const onKey = (e: KeyboardEvent) => {
    const at = enabled.findIndex((i) => i.id === value)
    let next = -1
    if (e.key === 'ArrowRight') next = (at + 1) % enabled.length
    else if (e.key === 'ArrowLeft') next = (at - 1 + enabled.length) % enabled.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = enabled.length - 1
    if (next < 0) return
    e.preventDefault()
    const item = enabled[next]
    if (!item) return
    onChange(item.id)
    refs.current[items.indexOf(item)]?.focus()
  }
  return (
    <div role="tablist" aria-label={label} onKeyDown={onKey} className={cn('flex border-b border-line', className)}>
      {items.map((item, i) => {
        const selected = item.id === value
        return (
          <button
            key={item.id}
            ref={(el) => {
              refs.current[i] = el
            }}
            id={tabId(base, item.id)}
            role="tab"
            type="button"
            aria-selected={selected}
            aria-controls={panelId(base, item.id)}
            tabIndex={selected ? 0 : -1}
            disabled={item.disabled}
            onClick={() => onChange(item.id)}
            className={cn(
              'relative flex flex-1 items-center justify-center gap-1.5 px-2 py-2.5 font-display text-[14px] font-semibold uppercase tracking-[0.06em] transition-colors',
              '[&_svg]:size-3.5',
              selected ? 'text-fg' : 'text-fg-dim hover:text-fg-muted',
              item.disabled && 'opacity-40',
            )}
          >
            {item.icon}
            {item.label}
            {selected ? (
              <motion.span
                layoutId={`${base}-indicator`}
                className="absolute inset-x-1 -bottom-px h-[2px] bg-hazard shadow-[0_0_10px_var(--color-hazard)]"
                transition={{ type: 'spring', stiffness: 500, damping: 38 }}
              />
            ) : null}
          </button>
        )
      })}
    </div>
  )
}
