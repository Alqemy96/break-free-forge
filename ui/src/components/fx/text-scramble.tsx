import { useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState, type ElementType } from 'react'

const GLYPHS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&@$/<>=+*'

/**
 * Motion Primitives-style "text scramble": characters resolve left to right out of noise.
 * Screen readers get the final text immediately (visually hidden copy); reduced motion shows it instantly.
 */
export function TextScramble({
  text,
  as: Tag = 'span',
  className,
  duration = 0.8,
  delay = 0,
  trigger,
  disabled = false,
}: {
  text: string
  as?: ElementType
  className?: string
  /** seconds */
  duration?: number
  /** seconds */
  delay?: number
  /** change this value to replay */
  trigger?: unknown
  /** render the text as-is (e.g. cards far down a long grid) */
  disabled?: boolean
}) {
  const reduce = useReducedMotion() || disabled
  const [shown, setShown] = useState(reduce ? text : '')
  const frame = useRef(0)

  useEffect(() => {
    if (reduce) {
      setShown(text)
      return
    }
    let start = 0
    const total = Math.max(1, duration * 1000)
    const wait = delay * 1000
    const tick = (now: number) => {
      if (!start) start = now
      const t = now - start - wait
      if (t < 0) {
        frame.current = requestAnimationFrame(tick)
        return
      }
      const progress = Math.min(1, t / total)
      const settled = Math.floor(progress * text.length)
      let out = ''
      for (let i = 0; i < text.length; i++) {
        const ch = text[i] ?? ''
        if (i < settled || ch === ' ') out += ch
        else out += GLYPHS[Math.floor(Math.random() * GLYPHS.length)] ?? ch
      }
      setShown(out)
      if (progress < 1) frame.current = requestAnimationFrame(tick)
      else setShown(text)
    }
    frame.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame.current)
  }, [text, duration, delay, reduce, trigger])

  return (
    <Tag className={className}>
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">{shown || '\u00a0'}</span>
    </Tag>
  )
}
