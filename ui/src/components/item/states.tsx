import { AlertTriangle, RotateCw, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** Comic art for empty and error states (original artwork, webp in public/art). */
export type StateArt = 'takeover' | 'ai-ally'

const ART: Record<StateArt, { src: string; alt: string; width: number; height: number; position: string }> = {
  takeover: {
    src: '/art/takeover.webp',
    alt: 'Comic panel: a gloved hand plugs a glowing drive into an opened console while digital chains break apart.',
    width: 800,
    height: 691,
    position: '60% 45%',
  },
  'ai-ally': {
    src: '/art/ai-ally.webp',
    alt: 'Comic panel: a masked figure in a hood works at a terminal while a glowing cyan face of an AI helps from the screen.',
    width: 800,
    height: 615,
    position: '50% 40%',
  },
}

function Art({ art, className }: { art: StateArt; className?: string }) {
  const a = ART[art]
  return (
    <img
      src={a.src}
      alt={a.alt}
      width={a.width}
      height={a.height}
      loading="lazy"
      decoding="async"
      className={cn('w-full border-2 border-black object-cover shadow-[4px_4px_0_var(--color-pink)]', className)}
      style={{ objectPosition: a.position }}
    />
  )
}

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  className,
  art,
}: {
  icon: LucideIcon
  title: string
  children?: ReactNode
  action?: ReactNode
  className?: string
  art?: StateArt
}) {
  return (
    <div className={cn('panel ink-edge relative flex flex-col items-center justify-center gap-3 px-6 py-10 text-center', className)}>
      {art ? <Art art={art} className="mb-2 h-44 max-w-xl sm:h-56" /> : null}
      <span className="grid size-12 place-items-center rounded-[2px] border-2 border-line-strong bg-surface-2 text-hazard">
        <Icon className="size-5" aria-hidden />
      </span>
      <h3 className="title-display slashes text-[22px] text-fg">{title}</h3>
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
  art,
}: {
  title?: string
  message: string
  code?: string
  onRetry?: () => void
  className?: string
  art?: StateArt
}) {
  return (
    <div role="alert" className={cn('relative overflow-hidden border-2 border-danger bg-danger/[0.07] px-5 py-4', className)}>
      <div aria-hidden className="hazard-stripes-dim absolute inset-y-0 left-0 w-1.5" />
      <div className="flex flex-col gap-3 pl-2 sm:flex-row sm:items-start">
        {art ? <Art art={art} className="h-28 sm:w-44 sm:shrink-0" /> : null}
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <AlertTriangle className="mt-0.5 size-5 shrink-0 text-danger" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="rgb-split font-display text-[17px] tracking-wide text-fg uppercase">{title}</p>
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
    </div>
  )
}
