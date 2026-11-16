import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from 'react'
import { cn } from '@/lib/utils'

export interface ChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'color'> {
  pressed: boolean
  /** CSS color for the active state (element/rarity token); defaults to hazard */
  color?: string
  icon?: ReactNode
}

/** A toggle chip (aria-pressed). Colour is never the only signal: active chips get a mark + weight. */
export function Chip({ pressed, color, icon, className, children, style, ...props }: ChipProps) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      style={{ ...(style ?? {}), '--chip': color ?? 'var(--color-hazard)' } as CSSProperties}
      className={cn(
        'group inline-flex h-8 items-center gap-1.5 rounded-[2px] border px-2.5 font-mono text-[11.5px] uppercase tracking-[0.06em] transition-[background-color,border-color,color] duration-150',
        '[&_svg]:size-3.5 [&_svg]:shrink-0',
        pressed
          ? 'border-[color:var(--chip)] bg-[color-mix(in_oklab,var(--chip)_16%,transparent)] font-semibold text-[color:var(--chip)]'
          : 'border-line bg-surface-2 text-fg-muted hover:border-line-strong hover:text-fg',
        className,
      )}
      {...props}
    >
      {icon}
      {children}
      {pressed ? <span aria-hidden className="ml-0.5 size-1.5 rounded-full bg-[color:var(--chip)] shadow-[0_0_8px_var(--chip)]" /> : null}
    </button>
  )
}
