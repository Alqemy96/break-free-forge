import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const field =
  'w-full rounded-[3px] border border-line-strong bg-bg/70 text-fg placeholder:text-fg-dim shadow-[inset_0_1px_2px_rgb(0_0_0/0.5)] transition-[border-color,box-shadow] duration-150 hover:border-fg-dim focus-visible:border-hazard focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_rgb(255_106_19/0.25)] disabled:opacity-50 aria-[invalid=true]:border-danger'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, type = 'text', ...props },
  ref,
) {
  return <input ref={ref} type={type} className={cn(field, 'h-10 px-3 text-[15px]', className)} {...props} />
})

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, ...props },
  ref,
) {
  return <textarea ref={ref} className={cn(field, 'min-h-20 px-3 py-2 text-[14px] leading-relaxed', className)} {...props} />
})

export const fieldClass = field
