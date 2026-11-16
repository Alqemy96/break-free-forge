import { Crosshair, Droplet, Flame, Radiation, Snowflake, Zap, type LucideIcon } from 'lucide-react'
import type { ElementId, ModuleState } from '@/api/types'
import type { RarityKey } from '@/lib/format'

/** CSS color for a rarity (design token). */
export function rarityColor(key: RarityKey): string {
  return `var(--color-rarity-${key})`
}

export function elementColor(id: ElementId | null): string {
  return id ? `var(--color-el-${id})` : 'var(--color-fg-dim)'
}

export const ELEMENT_ICONS: Record<ElementId, LucideIcon> = {
  cryo: Snowflake,
  fire: Flame,
  radiation: Radiation,
  shock: Zap,
  corrosive: Droplet,
  impact: Crosshair,
}

export const STATE_COLOR: Record<ModuleState, string> = {
  ok: 'var(--color-ok)',
  degraded: 'var(--color-warn)',
  failed: 'var(--color-danger)',
  blocked: 'var(--color-blocked)',
}

export const STATE_LABEL: Record<ModuleState, string> = {
  ok: 'OK',
  degraded: 'Degraded',
  failed: 'Failed',
  blocked: 'Blocked',
}
