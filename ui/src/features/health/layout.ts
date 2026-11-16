/** Layered layout for the module mesh: depth = longest `requires` chain. Pure, unit-tested. */
import type { ModuleRow } from '@/api/types'

export interface MeshNode {
  name: string
  depth: number
  x: number
  y: number
}

export interface MeshEdge {
  from: string
  to: string
}

export function moduleDepths(modules: Pick<ModuleRow, 'name' | 'requires'>[]): Map<string, number> {
  const byName = new Map(modules.map((m) => [m.name, m]))
  const depth = new Map<string, number>()
  const visiting = new Set<string>()
  const walk = (name: string): number => {
    const known = depth.get(name)
    if (known !== undefined) return known
    if (visiting.has(name)) return 0 // a cycle should never happen; do not hang if it does
    visiting.add(name)
    const reqs = byName.get(name)?.requires.filter((r) => byName.has(r)) ?? []
    const d = reqs.length ? Math.max(...reqs.map(walk)) + 1 : 0
    visiting.delete(name)
    depth.set(name, d)
    return d
  }
  for (const m of modules) walk(m.name)
  return depth
}

export function meshLayout(
  modules: Pick<ModuleRow, 'name' | 'requires'>[],
  width: number,
  height: number,
  pad = 70,
): { nodes: MeshNode[]; edges: MeshEdge[] } {
  const depth = moduleDepths(modules)
  const maxDepth = Math.max(0, ...depth.values())
  const columns = new Map<number, string[]>()
  for (const m of modules) {
    const d = depth.get(m.name) ?? 0
    columns.set(d, [...(columns.get(d) ?? []), m.name])
  }
  const nodes: MeshNode[] = []
  for (const [d, names] of columns) {
    const x = maxDepth === 0 ? width / 2 : pad + (d * (width - 2 * pad)) / maxDepth
    names.forEach((name, i) => {
      const slot = (height - 2 * pad) / Math.max(1, names.length)
      // a lone cell zig-zags around the centre line so long edges can arc clear of it
      const y = names.length === 1 && d > 0 ? height / 2 + (d % 2 === 1 ? -1 : 1) * slot * 0.13 : pad + slot * (i + 0.5)
      nodes.push({ name, depth: d, x, y })
    })
  }
  const known = new Set(modules.map((m) => m.name))
  const edges: MeshEdge[] = []
  for (const m of modules) for (const r of m.requires) if (known.has(r)) edges.push({ from: r, to: m.name })
  return { nodes, edges }
}
