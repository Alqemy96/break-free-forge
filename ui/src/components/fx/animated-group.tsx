import { motion, type Variants } from 'motion/react'
import type { ReactNode } from 'react'

const container: Variants = { hidden: {}, visible: {} }

/** Children pass `custom={index}`; the stagger is capped so a 200-card grid still lands fast. */
export const groupItem: Variants = {
  hidden: { opacity: 0, y: 14, filter: 'blur(4px)' },
  visible: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: { type: 'spring', stiffness: 380, damping: 32, delay: Math.min(i, 14) * 0.035 },
  }),
}

/**
 * Motion Primitives-style AnimatedGroup: children enter staggered (capped). Re-keys (e.g. a new search)
 * replay the entrance. MotionConfig reducedMotion="user" turns the movement off.
 */
export function AnimatedGroup({
  children,
  className,
  as = 'ul',
  label,
}: {
  children: ReactNode
  className?: string
  as?: 'ul' | 'div' | 'ol'
  label?: string
}) {
  const Comp = as === 'ul' ? motion.ul : as === 'ol' ? motion.ol : motion.div
  return (
    <Comp className={className} variants={container} initial="hidden" animate="visible" aria-label={label}>
      {children}
    </Comp>
  )
}
