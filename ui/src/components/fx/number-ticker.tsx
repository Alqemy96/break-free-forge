import { motion, useReducedMotion, useSpring, useTransform } from 'motion/react'
import { useEffect } from 'react'
import { formatInt } from '@/lib/format'

/** Motion Primitives-style AnimatedNumber: springs to each new value; tabular figures. */
export function NumberTicker({ value, className }: { value: number; className?: string }) {
  const reduce = useReducedMotion()
  const spring = useSpring(reduce ? value : 0, { stiffness: 90, damping: 20, mass: 0.8 })
  const text = useTransform(spring, (v) => formatInt(Math.round(v)))
  useEffect(() => {
    if (reduce) spring.jump(value)
    else spring.set(value)
  }, [value, reduce, spring])
  return (
    <span className={className}>
      <span className="sr-only">{formatInt(value)}</span>
      <motion.span aria-hidden className="tabular-nums">
        {text}
      </motion.span>
    </span>
  )
}
