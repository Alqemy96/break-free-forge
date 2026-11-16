import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function Kbd({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        'inline-flex h-5 min-w-5 items-center justify-center rounded-[2px] border border-line-strong border-b-2 bg-surface-3 px-1 font-mono text-[10.5px] leading-none text-fg-muted',
        className,
      )}
      {...props}
    />
  )
}

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden className={cn('skeleton rounded-[2px]', className)} {...props} />
}

export function Separator({ className, vertical = false }: { className?: string; vertical?: boolean }) {
  return (
    <div
      role="separator"
      aria-orientation={vertical ? 'vertical' : 'horizontal'}
      className={cn(vertical ? 'w-px self-stretch bg-line' : 'h-px w-full bg-line', className)}
    />
  )
}

/** "[ SECTION ]" telemetry heading */
export function SectionLabel({ children, className, as: Tag = 'h2' }: { children: ReactNode; className?: string; as?: 'h2' | 'h3' | 'p' }) {
  return (
    <Tag className={cn('micro flex items-center gap-2 text-fg-dim', className)}>
      <span aria-hidden className="text-hazard">[</span>
      <span className="text-fg-muted">{children}</span>
      <span aria-hidden className="text-hazard">]</span>
    </Tag>
  )
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn('inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent', className)}
    />
  )
}
