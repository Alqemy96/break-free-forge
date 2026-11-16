import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const field =
  'w-full rounded-[2px] border-2 border-line-strong bg-[#030406] text-fg placeholder:text-fg-dim font-mono transition-[border-color,box-shadow] duration-150 hover:border-fg-dim focus-visible:border-violet focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet disabled:opacity-50 aria-[invalid=true]:border-danger'

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
