/**
 * Which silhouette an item gets. Pure and unit-tested. Inputs are whatever the API already returns:
 * search rows carry `type` ("weapon" | "shield" | "classmod" | "repair_kit" | "gadget" | "enhancement")
 * and `weapon_type`; the dossier only has the decoded `category` text. Anything unrecognised maps to
 * "unknown" (a generic crate), never a guess.
 */
export type IconKind =
  | 'pistol'
  | 'smg'
  | 'shotgun'
  | 'assault_rifle'
  | 'sniper'
  | 'heavy'
  | 'shield'
  | 'grenade'
  | 'classmod'
  | 'repkit'
  | 'enhancement'
  | 'unknown'

export const ICON_KINDS: readonly IconKind[] = [
  'pistol',
  'smg',
  'shotgun',
  'assault_rifle',
  'sniper',
  'heavy',
  'shield',
  'grenade',
  'classmod',
  'repkit',
  'enhancement',
  'unknown',
]

export const ICON_LABEL: Record<IconKind, string> = {
  pistol: 'Pistol',
  smg: 'SMG',
  shotgun: 'Shotgun',
  assault_rifle: 'Assault rifle',
  sniper: 'Sniper',
  heavy: 'Heavy weapon',
  shield: 'Shield',
  grenade: 'Grenade / ordnance',
  classmod: 'Class mod',
  repkit: 'Repair kit',
  enhancement: 'Enhancement',
  unknown: 'Item',
}

const norm = (text: string | null | undefined): string => (text ?? '').toLowerCase().replace(/[^a-z]+/g, '')

/** Match one normalised token (a weapon_type, a type, or a category word). */
function fromToken(token: string): IconKind | null {
  if (!token) return null
  if (token.includes('pistol')) return 'pistol'
  if (token.includes('smg') || token.includes('submachine')) return 'smg'
  if (token.includes('shotgun')) return 'shotgun'
  if (token.includes('assaultrifle') || token === 'ar') return 'assault_rifle'
  if (token.includes('sniper')) return 'sniper'
  if (token.includes('heavy') || token.includes('launcher')) return 'heavy'
  if (token.includes('shield')) return 'shield'
  if (token.includes('grenade') || token.includes('gadget') || token.includes('ordnance')) return 'grenade'
  if (token.includes('classmod')) return 'classmod'
  if (token.includes('repair') || token.includes('repkit')) return 'repkit'
  if (token.includes('enhancement')) return 'enhancement'
  return null
}

export function iconKindOf(input: { type?: string | null; weaponType?: string | null; category?: string | null }): IconKind {
  // weapon_type is the most specific; then the item type; then free-text category
  return fromToken(norm(input.weaponType)) ?? fromToken(norm(input.type)) ?? fromToken(norm(input.category)) ?? 'unknown'
}
