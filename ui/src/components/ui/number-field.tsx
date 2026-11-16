import { Minus, Plus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { fieldClass } from './input'

/** Integer input with stepper buttons. `value` null = blank (meaning is up to the caller). */
export function NumberField({
  id,
  value,
  onChange,
  min,
  max,
  placeholder,
  className,
  ariaLabel,
  describedBy,
}: {
  id: string
  value: number | null
  onChange: (value: number | null) => void
  min: number
  max: number
  placeholder?: string
  className?: string
  ariaLabel?: string
  describedBy?: string
}) {
  const clamp = (n: number) => Math.min(max, Math.max(min, Math.trunc(n)))
  const step = (d: number) => onChange(clamp((value ?? (d > 0 ? min - 1 : max + 1)) + d))
  return (
    <div className={cn('flex h-10 items-stretch', className)}>
      <button
        type="button"
        aria-label="Decrease"
        tabIndex={-1}
        onClick={() => step(-1)}
        className="grid w-8 place-items-center rounded-l-[3px] border border-r-0 border-line-strong bg-surface-3 text-fg-muted hover:text-fg"
      >
        <Minus className="size-3.5" />
      </button>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        value={value ?? ''}
        placeholder={placeholder}
        aria-label={ariaLabel}
        aria-describedby={describedBy}
        onChange={(e) => {
          const text = e.target.value
          if (text === '') return onChange(null)
          const n = Number(text)
          if (Number.isFinite(n)) onChange(clamp(n))
        }}
        className={cn(fieldClass, 'w-full min-w-0 rounded-none text-center font-mono text-[15px]')}
      />
      <button
        type="button"
        aria-label="Increase"
        tabIndex={-1}
        onClick={() => step(1)}
        className="grid w-8 place-items-center rounded-r-[3px] border border-l-0 border-line-strong bg-surface-3 text-fg-muted hover:text-fg"
      >
        <Plus className="size-3.5" />
      </button>
    </div>
  )
}
