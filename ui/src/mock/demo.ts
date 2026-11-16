/**
 * Fictional demo catalog for mock mode when the captured fixtures hold no items (the public tree
 * ships no game data). Everything here is invented: made-up makers ("Breakfree Arms", "Ajar
 * Industries", "Lockpick & Sons"), made-up item names, and placeholder serials that merely start with
 * "@U" so the mock decoder accepts them. None of it is real game data and none of the serials decode
 * anywhere. Only imported by mockApi.ts (dropped from production builds with the rest of the mock).
 */
import type { ElementId, IdentifyPart, IdentifyResponse, SearchResultRow, Stats } from '@/api/types'

interface Demo {
  slug: string
  name: string
  type: string
  weaponType: string
  maker: string
  rarity: string
  element: ElementId | null
  level: number
  category: string
  parts: string[]
}

const BF = 'Breakfree Arms'
const AJ = 'Ajar Industries'
const LP = 'Lockpick & Sons'

const DEMOS: Demo[] = [
  { slug: 'crowbar', name: 'Crowbar Mk II', type: 'weapon', weaponType: 'pistol', maker: BF, rarity: 'Legendary', element: 'shock', level: 60, category: 'Pistol', parts: ['Crowbar frame, ported', 'Long jaw barrel', 'Shock coil', 'Extended stack (+8)', 'Splitter grip', 'Open-loop trigger'] },
  { slug: 'skeleton', name: 'Skeleton Key', type: 'weapon', weaponType: 'smg', maker: AJ, rarity: 'Epic', element: 'cryo', level: 60, category: 'SMG', parts: ['Pass-key receiver', 'Slim barrel', 'Cryo coil', 'Drum mag', 'Folding stock'] },
  { slug: 'unlatch', name: 'Unlatch', type: 'weapon', weaponType: 'shotgun', maker: LP, rarity: 'Rare', element: 'fire', level: 58, category: 'Shotgun', parts: ['Hinge receiver', 'Wide choke', 'Ember chamber', 'Pump grip'] },
  { slug: 'sesame', name: 'Open Sesame', type: 'weapon', weaponType: 'pistol', maker: BF, rarity: 'Epic', element: 'corrosive', level: 60, category: 'Pistol', parts: ['Latch frame', 'Short barrel', 'Acid sac', 'Spring mag'] },
  { slug: 'jailbreak', name: 'Jailbreak', type: 'weapon', weaponType: 'smg', maker: AJ, rarity: 'Uncommon', element: null, level: 55, category: 'SMG', parts: ['Plain receiver', 'Standard barrel', 'Straight mag'] },
  { slug: 'prybar', name: 'Pry Bar', type: 'weapon', weaponType: 'shotgun', maker: BF, rarity: 'Legendary', element: 'radiation', level: 60, category: 'Shotgun', parts: ['Lever frame', 'Cut-down barrel', 'Isotope cell', 'Wedge stock'] },
  { slug: 'lockjaw', name: 'Lockjaw AR-9', type: 'weapon', weaponType: 'assaultrifle', maker: LP, rarity: 'Rare', element: 'impact', level: 57, category: 'Assault Rifle', parts: ['Jaw receiver', 'Carbine barrel', 'Ring sight', 'Box mag'] },
  { slug: 'tumbler', name: 'The Tumbler', type: 'weapon', weaponType: 'sniper', maker: AJ, rarity: 'Legendary', element: 'shock', level: 60, category: 'Sniper Rifle', parts: ['Pin-stack receiver', 'Fluted barrel', 'Arc coil', 'Cheek rest', 'Scope rail'] },
  { slug: 'wrecker', name: 'Wrecking Door', type: 'weapon', weaponType: 'heavy', maker: BF, rarity: 'Epic', element: 'fire', level: 60, category: 'Heavy Weapon', parts: ['Ram frame', 'Wide muzzle', 'Fuel tank'] },
  { slug: 'deadbolt', name: 'Deadbolt', type: 'shield', weaponType: '', maker: LP, rarity: 'Legendary', element: null, level: 60, category: 'Shield', parts: ['Bolt plate', 'Strike capacitor', 'Reinforced hinge'] },
  { slug: 'hacksaw', name: 'Hacksaw Cell', type: 'shield', weaponType: '', maker: AJ, rarity: 'Rare', element: null, level: 58, category: 'Shield', parts: ['Serrated plate', 'Basic capacitor'] },
  { slug: 'popper', name: 'Lock Popper', type: 'gadget', weaponType: '', maker: BF, rarity: 'Epic', element: 'fire', level: 60, category: 'Grenade', parts: ['Fuse housing', 'Ember charge', 'Sticky coat'] },
  { slug: 'mask', name: 'Blank Face', type: 'classmod', weaponType: '', maker: AJ, rarity: 'Legendary', element: null, level: 60, category: 'Class Mod (Demo)', parts: ['Visor core', 'Crack-line skill chip', 'Quiet-step firmware'] },
  { slug: 'patch', name: 'Patch Kit', type: 'repair_kit', weaponType: '', maker: LP, rarity: 'Rare', element: null, level: 56, category: 'Repair Kit', parts: ['Field housing', 'Quick-clot dose'] },
  { slug: 'overclock', name: 'Overclock Chip', type: 'enhancement', weaponType: '', maker: AJ, rarity: 'Epic', element: null, level: 60, category: 'Enhancement', parts: ['Heat sink', 'Open bus'] },
]

const serialOf = (d: Demo, level = d.level) => `@UDEMO-${d.slug}-L${level}-0001-notarealserial`

const isWeapon = (d: Demo) => d.type === 'weapon'

function partsOf(d: Demo): IdentifyPart[] {
  return d.parts.map((label, position) => ({
    position,
    token_index: 10 + position,
    label,
    category_id: 900,
    index: position + 1,
    raw: `demo_${d.slug}_${position}`,
    category_link: null,
  }))
}

export function demoPool(): SearchResultRow[] {
  return DEMOS.map((d) => ({
    serial: serialOf(d),
    name: d.name,
    type: d.type,
    weapon_type: d.weaponType,
    manufacturer: d.maker,
    label: `${d.maker} ${d.category}`,
    rarity: d.rarity,
    element: d.element,
    source: d.type === 'classmod' ? 'demo fixtures (fictional) locksmith' : 'demo fixtures (fictional)',
    level: d.level,
    decoded: { display_name: d.name, category: d.category, rarity: d.rarity, element: d.element, owned: true, warnings: [] },
  }))
}

export function demoIdentify(): Record<string, IdentifyResponse> {
  const out: Record<string, IdentifyResponse> = {}
  DEMOS.forEach((d, i) => {
    const serial = serialOf(d)
    const warn = d.slug === 'crowbar' ? ['Magazine part is outside the usual range (demo warning).'] : []
    out[serial] = {
      serial,
      info: {
        serial,
        category_id: 900 + i,
        category: d.category,
        level: d.level,
        rarity: d.rarity,
        element: d.element,
        legendary_name: d.rarity === 'Legendary' ? d.name : null,
        display_name: d.name,
        parts: [],
        other_components: d.rarity === 'Legendary' ? [['Epic', `${d.name} core`]] : [],
        tokens: `demo-token-stream ${d.slug} ${d.parts.length} parts (fictional)`,
        content_pack: 'coregame',
        content_pack_label: 'Core game (demo)',
        owned: true,
        manifest_ok: true,
        warnings: warn,
      },
      odds: d.rarity === 'Legendary' ? 'Demo drop table: about 1 in 2,000 from the Vault Keeper (fictional).' : 'Demo drop table: common world drop (fictional).',
      parts: partsOf(d),
      problems: [],
      is_weapon: isWeapon(d),
      can_set_element: isWeapon(d),
    }
  })
  return out
}

export function demoStats(): Stats {
  const count = <K extends string>(pick: (d: Demo) => K | null): Record<string, number> => {
    const r: Record<string, number> = {}
    for (const d of DEMOS) {
      const k = pick(d)
      if (k) r[k] = (r[k] ?? 0) + 1
    }
    return r
  }
  return {
    by_type: count((d) => d.type),
    by_weapon_type: count((d) => d.weaponType || null),
    by_rarity: count((d) => d.rarity),
    by_manufacturer: count((d) => d.maker),
    by_element: count((d) => d.element),
    by_character: {},
  } as Stats
}

export const DEMO_COUNT = DEMOS.length
