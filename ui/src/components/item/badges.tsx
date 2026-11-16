import type { CSSProperties } from 'react'
import type { ElementId } from '@/api/types'
import { elementKey, elementLabel, rarityKey } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ELEMENT_ICONS, elementColor, rarityColor } from './tokens'

const base =
  'inline-flex items-center gap-1 whitespace-nowrap rounded-[2px] border px-1.5 py-[3px] font-cond text-[12px] font-bold uppercase leading-none tracking-[0.1em]'

export function RarityBadge({ rarity, className }: { rarity: string | null | undefined; className?: string }) {
  const key = rarityKey(rarity)
  const style = { '--c': rarityColor(key) } as CSSProperties
  return (
    <span
      style={style}
      className={cn(base, 'border-[color-mix(in_oklab,var(--c)_45%,transparent)] bg-[color-mix(in_oklab,var(--c)_12%,transparent)] text-[color:var(--c)]', className)}
    >
      <span aria-hidden className="size-1.5 rotate-45 bg-[color:var(--c)]" />
      <span className={key === 'pearl' ? 'pearl-shimmer' : undefined}>{rarity || 'Unknown rarity'}</span>
    </span>
  )
}

export function ElementIcon({ element, className }: { element: ElementId; className?: string }) {
  const Icon = ELEMENT_ICONS[element]
  return (
    <Icon
      aria-hidden
      className={cn('size-3', className)}
      style={element === 'shock' ? { color: 'var(--color-el-shock-spark)' } : undefined}
    />
  )
}

/** Element badge. Gear (no element) renders nothing unless `showNone`. */
export function ElementBadge({
  element,
  className,
  showNone = false,
}: {
  element: string | null | undefined
  className?: string
  showNone?: boolean
}) {
  const key = elementKey(element)
  if (!key) {
    return showNone ? <span className={cn(base, 'border-line bg-surface-2 text-fg-dim', className)}>No element</span> : null
  }
  const style = { '--c': elementColor(key) } as CSSProperties
  return (
    <span
      style={style}
      className={cn(base, 'border-[color-mix(in_oklab,var(--c)_45%,transparent)] bg-[color-mix(in_oklab,var(--c)_11%,transparent)] text-[color:var(--c)]', className)}
    >
      <ElementIcon element={key} />
      {elementLabel(key)}
    </span>
  )
}
