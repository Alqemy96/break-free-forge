import { AlertTriangle, RotateCw, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  className,
}: {
  icon: LucideIcon
  title: string
  children?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('relative flex flex-col items-center justify-center gap-3 border border-dashed border-line-strong px-6 py-14 text-center', className)}>
      <span aria-hidden className="absolute top-2 left-2 size-2 border-t border-l border-hazard" />
      <span aria-hidden className="absolute right-2 bottom-2 size-2 border-r border-b border-hazard" />
      <span className="grid size-12 place-items-center rounded-[3px] border border-line-strong bg-surface-2 text-fg-muted">
        <Icon className="size-5" aria-hidden />
      </span>
      <h3 className="title-display text-[22px] text-fg">{title}</h3>
      {children ? <div className="max-w-md text-[14px] text-fg-muted">{children}</div> : null}
      {action}
    </div>
  )
}

/** An error from the server, shown with its own message and a retry. */
export function ErrorState({
  title = 'That did not work',
  message,
  code,
  onRetry,
  className,
}: {
  title?: string
  message: string
  code?: string
  onRetry?: () => void
  className?: string
}) {
  return (
    <div role="alert" className={cn('relative overflow-hidden border border-danger/40 bg-danger/[0.06] px-5 py-4', className)}>
      <div aria-hidden className="hazard-stripes-dim absolute inset-y-0 left-0 w-1.5" />
      <div className="flex items-start gap-3 pl-2">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-danger" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="font-display text-[17px] font-semibold uppercase tracking-wide text-fg">{title}</p>
          <p className="mt-1 text-[14px] break-words text-fg-muted">{message}</p>
          {code ? <p className="micro mt-2 text-fg-dim">code: {code}</p> : null}
        </div>
        {onRetry ? (
          <Button size="sm" variant="secondary" onClick={onRetry}>
            <RotateCw /> Retry
          </Button>
        ) : null}
      </div>
    </div>
  )
}
