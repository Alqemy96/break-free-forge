import type { LabelHTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function Label({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn('micro text-fg-muted', className)} {...props} />
}

/** A labelled control with optional hint text below (shadcn "Field" in spirit). */
export function Field({
  label,
  htmlFor,
  hint,
  className,
  children,
  aside,
}: {
  label: ReactNode
  htmlFor?: string
  hint?: ReactNode
  className?: string
  children: ReactNode
  aside?: ReactNode
}) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-1.5', className)}>
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={htmlFor}>{label}</Label>
        {aside}
      </div>
      {children}
      {hint ? <p className="text-[12.5px] leading-snug text-fg-dim">{hint}</p> : null}
    </div>
  )
}

/** fieldset + legend for chip groups */
export function FieldSet({ legend, children, className, aside }: { legend: ReactNode; children: ReactNode; className?: string; aside?: ReactNode }) {
  return (
    <fieldset className={cn('m-0 flex min-w-0 flex-col gap-2 border-0 p-0', className)}>
      <div className="flex items-baseline justify-between gap-2">
        <legend className="micro float-left p-0 text-fg-muted">{legend}</legend>
        {aside}
      </div>
      {children}
    </fieldset>
  )
}
