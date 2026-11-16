import { describe, expect, it } from 'vitest'
import { meshLayout, moduleDepths } from './layout'

const MODULES = [
  { name: 'codec', requires: [] },
  { name: 'data', requires: [] },
  { name: 'rules', requires: ['codec', 'data'] },
  { name: 'ops', requires: ['codec', 'data', 'rules'] },
  { name: 'catalog', requires: ['codec', 'data', 'rules', 'ops'] },
  { name: 'builder', requires: ['catalog', 'ops'] },
  { name: 'render', requires: [] },
]

describe('mesh layout', () => {
  it('layers modules by their longest requires chain', () => {
    const d = moduleDepths(MODULES)
    expect(Object.fromEntries(d)).toEqual({ codec: 0, data: 0, rules: 1, ops: 2, catalog: 3, builder: 4, render: 0 })
  })

  it('places every node inside the box and draws one edge per requirement', () => {
    const { nodes, edges } = meshLayout(MODULES, 1000, 400)
    expect(nodes).toHaveLength(7)
    for (const n of nodes) {
      expect(n.x).toBeGreaterThanOrEqual(0)
      expect(n.x).toBeLessThanOrEqual(1000)
      expect(n.y).toBeGreaterThanOrEqual(0)
      expect(n.y).toBeLessThanOrEqual(400)
    }
    expect(edges).toHaveLength(2 + 3 + 4 + 2)
    expect(edges).toContainEqual({ from: 'catalog', to: 'builder' })
  })

  it('survives unknown requirements and cycles', () => {
    const d = moduleDepths([
      { name: 'a', requires: ['b', 'ghost'] },
      { name: 'b', requires: ['a'] },
    ])
    expect(d.size).toBe(2)
  })
})
