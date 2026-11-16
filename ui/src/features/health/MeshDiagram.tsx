import { motion, useReducedMotion } from 'motion/react'
import { useMemo, type KeyboardEvent } from 'react'
import type { ModuleRow, ModuleState } from '@/api/types'
import { STATE_COLOR, STATE_LABEL } from '@/components/item/tokens'
import { cn } from '@/lib/utils'
import { meshLayout, type MeshNode } from './layout'

const W = 1000
const H = 430
const R = 40
export const OUTER = 'web'

/** Neighbouring columns: a side-to-side S curve. Longer spans arc over (or under) the cells between. */
function edgePath(a: MeshNode, b: MeshNode): string {
  const span = Math.abs(b.depth - a.depth)
  if (span <= 1) {
    const x1 = a.x + R * 0.87
    const x2 = b.x - R * 0.87
    const mid = (x1 + x2) / 2
    return `M${x1},${a.y} C${mid},${a.y} ${mid},${b.y} ${x2},${b.y}`
  }
  const up = (a.y + b.y) / 2 <= H / 2
  const bow = 26 + 30 * (span - 1)
  const peak = up ? Math.max(10, Math.min(a.y, b.y) - bow) : Math.min(H - 10, Math.max(a.y, b.y) + bow)
  const y1 = a.y + (up ? -R : R)
  const y2 = b.y + (up ? -R : R)
  return `M${a.x},${y1} C${a.x + 30},${peak} ${b.x - 30},${peak} ${b.x},${y2}`
}

function hexPoints(cx: number, cy: number, r: number): string {
  const pts: string[] = []
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i + Math.PI / 6
    pts.push(`${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`)
  }
  return pts.join(' ')
}

/**
 * The seven cells as a living mesh: nodes coloured by state, edges are `requires`. Hover or focus a
 * cell to light up its neighbours; Enter/Space pins it in the detail panel.
 */
export function MeshDiagram({
  modules,
  active,
  onActive,
  onPin,
}: {
  modules: ModuleRow[]
  active: string | null
  onActive: (name: string | null) => void
  onPin: (name: string) => void
}) {
  const reduce = useReducedMotion()
  const sinks = useMemo(
    () => modules.filter((m) => !modules.some((o) => o.requires.includes(m.name))).map((m) => m.name),
    [modules],
  )
  const { nodes, edges } = useMemo(
    () => meshLayout([...modules, { name: OUTER, requires: sinks }], W, H),
    [modules, sinks],
  )
  const byName = new Map(modules.map((m) => [m.name, m]))
  const pos = new Map(nodes.map((n) => [n.name, n]))
  const related = new Set<string>()
  if (active) {
    related.add(active)
    for (const e of edges) {
      if (e.from === active) related.add(e.to)
      if (e.to === active) related.add(e.from)
    }
  }

  const stateOf = (name: string): ModuleState | 'outer' => byName.get(name)?.state ?? 'outer'
  const colorOf = (name: string) => {
    const st = stateOf(name)
    return st === 'outer' ? 'var(--color-violet-hi)' : STATE_COLOR[st]
  }

  const onKey = (e: KeyboardEvent, name: string) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onPin(name)
    }
  }

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full"
      role="group"
      aria-label="Module dependency mesh. Each cell is a module; lines point from a module to the modules that need it."
    >
      <defs>
        <pattern id="mesh-grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M40 0H0V40" fill="none" stroke="var(--color-line)" strokeWidth="0.6" opacity="0.6" />
        </pattern>
        <filter id="mesh-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="6" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <rect width={W} height={H} fill="url(#mesh-grid)" opacity="0.5" />

      <g aria-hidden>
        {edges.map((e) => {
          const a = pos.get(e.from)
          const b = pos.get(e.to)
          if (!a || !b) return null
          const st = stateOf(e.from)
          const broken = st === 'failed' || st === 'blocked'
          const dim = active !== null && !(related.has(e.from) && related.has(e.to) && (e.from === active || e.to === active))
          const d = edgePath(a, b)
          return (
            <g key={`${e.from}-${e.to}`} opacity={dim ? 0.15 : 1} style={{ transition: 'opacity .2s' }}>
              <path d={d} fill="none" stroke={colorOf(e.from)} strokeOpacity={0.22} strokeWidth={6} />
              <path
                d={d}
                fill="none"
                stroke={colorOf(e.from)}
                strokeWidth={1.6}
                strokeDasharray={broken ? '4 6' : '6 6'}
                className={!broken && !reduce ? 'animate-flow' : undefined}
              />
            </g>
          )
        })}
      </g>

      {nodes.map((n, i) => {
        const m = byName.get(n.name)
        const outer = n.name === OUTER
        const st = stateOf(n.name)
        const color = colorOf(n.name)
        const isActive = active === n.name
        const dim = active !== null && !related.has(n.name)
        const checks = m ? `${m.checks.filter((c) => c.ok).length}/${m.checks.length}` : ''
        const label = outer
          ? 'web, the outer layer: this UI and the API use every module through the Forge'
          : `${n.name}: ${STATE_LABEL[st as ModuleState]}. ${m?.purpose ?? ''} ${checks} checks passed.`
        return (
          <motion.g
            key={n.name}
            role="button"
            tabIndex={0}
            aria-label={label}
            aria-pressed={isActive}
            onPointerEnter={() => onActive(n.name)}
            onPointerLeave={() => onActive(null)}
            onFocus={() => onActive(n.name)}
            onBlur={() => onActive(null)}
            onClick={() => onPin(n.name)}
            onKeyDown={(e) => onKey(e, n.name)}
            initial={reduce ? false : { opacity: 0, scale: 0.6 }}
            animate={{ opacity: dim ? 0.35 : 1, scale: 1 }}
            transition={{ type: 'spring', stiffness: 300, damping: 24, delay: reduce ? 0 : i * 0.05 }}
            style={{ transformOrigin: `${n.x}px ${n.y}px`, outline: 'none' }}
            className="group cursor-pointer"
          >
            {st === 'failed' || st === 'blocked' ? (
              <circle cx={n.x} cy={n.y} r={R + 10} fill="none" stroke={color} strokeWidth={1} opacity={0.5} className={reduce ? undefined : 'animate-ping'} style={{ transformOrigin: `${n.x}px ${n.y}px` }} />
            ) : null}
            <polygon
              points={hexPoints(n.x, n.y, R + 7)}
              fill="none"
              stroke={color}
              strokeWidth={1}
              opacity={isActive ? 0.9 : 0}
              className="transition-opacity group-focus-visible:opacity-100"
            />
            <polygon
              points={hexPoints(n.x, n.y, R)}
              fill={outer ? 'var(--color-violet-deep)' : 'var(--color-surface-2)'}
              stroke={color}
              strokeWidth={isActive ? 2.5 : 1.6}
              strokeDasharray={outer ? '5 4' : undefined}
              filter={st === 'failed' || isActive ? 'url(#mesh-glow)' : undefined}
            />
            <text x={n.x} y={n.y - 2} textAnchor="middle" className={cn('fill-fg font-mono text-[14px] font-medium uppercase')} style={{ letterSpacing: '0.06em' }}>
              {n.name}
            </text>
            <text x={n.x} y={n.y + 15} textAnchor="middle" className="font-mono text-[10px] uppercase" fill={color} style={{ letterSpacing: '0.08em' }}>
              {outer ? 'outer' : st === 'ok' ? `OK ${checks}` : STATE_LABEL[st as ModuleState]}
            </text>
          </motion.g>
        )
      })}
    </svg>
  )
}
