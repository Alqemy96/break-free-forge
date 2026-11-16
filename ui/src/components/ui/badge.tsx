import { cva, type VariantProps } from 'class-variance-authority'
import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export const badgeVariants = cva(
  'inline-flex items-center gap-1 whitespace-nowrap rounded-[2px] border px-1.5 py-[3px] font-mono text-[10.5px] font-medium uppercase leading-none tracking-[0.08em] [&_svg]:size-3 [&_svg]:shrink-0',
  {
    variants: {
      tone: {
        neutral: 'border-line-strong bg-surface-3 text-fg-muted',
        hazard: 'border-hazard/50 bg-hazard/10 text-hazard-hi',
        violet: 'border-violet/50 bg-violet-deep/70 text-violet-hi',
        ok: 'border-ok/40 bg-ok/10 text-ok',
        warn: 'border-warn/40 bg-warn/10 text-warn',
        danger: 'border-danger/40 bg-danger/10 text-danger',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
)

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />
}
