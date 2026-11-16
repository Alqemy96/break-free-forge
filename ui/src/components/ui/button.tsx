import { cva, type VariantProps } from 'class-variance-authority'
import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export const buttonVariants = cva(
  [
    'relative inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-[2px]',
    'glitch font-display uppercase tracking-[0.05em] transition-[background-color,border-color,color,box-shadow,transform] duration-150 ease-[var(--ease-snap)]',
    'active:translate-y-px disabled:pointer-events-none disabled:opacity-45',
    '[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*=size-])]:size-4',
  ].join(' '),
  {
    variants: {
      variant: {
        primary:
          'border-2 border-black bg-hazard text-hazard-ink shadow-[3px_3px_0_var(--color-pink)] hover:bg-hazard-hi hover:text-hazard-ink',
        secondary:
          'border-2 border-line-strong bg-surface-3 text-fg shadow-[3px_3px_0_#000] hover:border-fg-dim hover:bg-surface-4',
        ghost: 'text-fg-muted hover:bg-surface-3 hover:text-fg',
        outline: 'border-2 border-line-strong bg-transparent text-fg hover:border-hazard hover:text-hazard-hi',
        violet:
          'border-2 border-black bg-violet text-[#04201d] shadow-[3px_3px_0_var(--color-pink)] hover:bg-violet-hi hover:text-[#04201d]',
        danger: 'border-2 border-danger/60 bg-transparent text-danger hover:bg-danger/10',
      },
      size: {
        sm: 'h-8 px-3 text-[12.5px]',
        md: 'h-10 px-4 text-[14px]',
        lg: 'h-12 px-6 text-[16px]',
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
