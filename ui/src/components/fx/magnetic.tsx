import { motion, useMotionValue, useReducedMotion, useSpring } from 'motion/react'
import { useRef, type PointerEvent, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** Motion Primitives-style Magnetic: the child drifts toward the pointer while it is near. */
export function Magnetic({
  children,
  strength = 0.22,
  range = 90,
  className,
}: {
  children: ReactNode
  strength?: number
  range?: number
  className?: string
}) {
  const reduce = useReducedMotion()
  const ref = useRef<HTMLDivElement>(null)
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const sx = useSpring(x, { stiffness: 260, damping: 18, mass: 0.4 })
  const sy = useSpring(y, { stiffness: 260, damping: 18, mass: 0.4 })

  const onMove = (e: PointerEvent) => {
    if (reduce || !ref.current || e.pointerType !== 'mouse') return
    const r = ref.current.getBoundingClientRect()
    const dx = e.clientX - (r.left + r.width / 2)
    const dy = e.clientY - (r.top + r.height / 2)
    const near = Math.hypot(dx, dy) < range + Math.max(r.width, r.height) / 2
    x.set(near ? dx * strength : 0)
    y.set(near ? dy * strength : 0)
  }
  const reset = () => {
    x.set(0)
    y.set(0)
  }
  return (
    <motion.div
      ref={ref}
      className={cn('inline-flex', className)}
      style={reduce ? undefined : { x: sx, y: sy }}
      onPointerMove={onMove}
      onPointerLeave={reset}
    >
      {children}
    </motion.div>
  )
}
