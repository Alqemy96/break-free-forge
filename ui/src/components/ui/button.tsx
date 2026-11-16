import { cva, type VariantProps } from 'class-variance-authority'
import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export const buttonVariants = cva(
  [
    'relative inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-[3px]',
    'font-display font-semibold uppercase tracking-[0.06em] transition-[background-color,border-color,color,box-shadow,transform] duration-150 ease-[var(--ease-snap)]',
    'active:translate-y-px disabled:pointer-events-none disabled:opacity-45',
    '[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*=size-])]:size-4',
  ].join(' '),
  {
    variants: {
      variant: {
        primary:
          'bg-hazard text-hazard-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.35),0_0_0_1px_rgb(255_106_19/0.6),0_8px_24px_-10px_rgb(255_106_19/0.7)] hover:bg-hazard-hi',
        secondary:
          'border border-line-strong bg-surface-3 text-fg shadow-[inset_0_1px_0_rgb(255_255_255/0.05)] hover:border-fg-dim hover:bg-surface-4',
        ghost: 'text-fg-muted hover:bg-surface-3 hover:text-fg',
        outline: 'border border-line-strong bg-transparent text-fg hover:border-hazard hover:text-hazard-hi',
        violet:
          'border border-violet/70 bg-violet-deep text-violet-hi shadow-[inset_0_1px_0_rgb(255_255_255/0.06)] hover:border-violet-hi hover:text-white',
        danger: 'border border-danger/50 bg-transparent text-danger hover:bg-danger/10',
      },
      size: {
        sm: 'h-8 px-3 text-[13px]',
        md: 'h-10 px-4 text-[15px]',
        lg: 'h-12 px-6 text-[17px]',
        icon: 'size-9 p-0',
        'icon-sm': 'size-8 p-0',
      },
    },
    defaultVariants: { variant: 'secondary', size: 'md' },
  },
)

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, type = 'button', ...props },
  ref,
) {
  return <button ref={ref} type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
})
