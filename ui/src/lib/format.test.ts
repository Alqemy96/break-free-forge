import { describe, expect, it } from 'vitest'
import {
  clampLimit,
  elementKey,
  elementLabel,
  formatDiffValue,
  formatInt,
  hiddenLine,
  hiddenTotal,
  kindOfType,
  parseLevel,
  plural,
  rarityKey,
  sentence,
  serialDiffParts,
  slugify,
  titleCase,
  truncateSerial,
} from './format'

describe('format', () => {
  it('rarityKey normalises names and tolerates junk', () => {
    expect(rarityKey('Legendary')).toBe('legendary')
    expect(rarityKey(' pearlescent ')).toBe('pearl')
    expect(rarityKey('VILE')).toBe('vile')
    expect(rarityKey(null)).toBe('unknown')
    expect(rarityKey('mythic')).toBe('unknown')
  })

  it('elementKey follows the vocab aliases', () => {
    expect(elementKey('Electric')).toBe('shock')
    expect(elementKey('incendiary')).toBe('fire')
    expect(elementKey('kinetic')).toBe('impact')
    expect(elementKey('')).toBeNull()
    expect(elementKey('plasma')).toBeNull()
    expect(elementLabel('cryo')).toBe('Cryo')
    expect(elementLabel(null)).toBe('No element')
  })

  it('formats integers and plurals with fixed grouping', () => {
    expect(formatInt(9875)).toBe('9,875')
    expect(formatInt(Number.NaN)).toBe('-')
    expect(plural(1, 'code')).toBe('1 code')
    expect(plural(2, 'match', 'matches')).toBe('2 matches')
  })

  it('truncates serials keeping both ends', () => {
    const s = '@Uge(J0FnkbUI5tpDRG}7is757fxX?}1Kh#K6KUAgOp#Gpzp-!Q8q0%7$'
    expect(truncateSerial(s)).toBe(`${s.slice(0, 12)}…${s.slice(-6)}`)
    expect(truncateSerial(s, 4, 2)).toBe('@Uge…7$')
    expect(truncateSerial('@Ushort')).toBe('@Ushort')
  })

  it('parses levels and limits into the contract ranges', () => {
    expect(parseLevel('60')).toBe(60)
    expect(parseLevel(' 7 ')).toBe(7)
    expect(parseLevel('0')).toBeNull()
    expect(parseLevel('101')).toBeNull()
    expect(parseLevel('')).toBeNull()
    expect(parseLevel('abc')).toBeNull()
    expect(clampLimit(500)).toBe(200)
    expect(clampLimit(0)).toBe(1)
    expect(clampLimit('x')).toBe(25)
  })

  it('describes hidden packs honestly', () => {
    const a = { pack: 'bounty_pack_3', label: 'Bounty Pack 3 - A Zane to Kill For', count: 26 }
    const b = { pack: 'story_pack_1', label: '', count: 4 }
    expect(hiddenLine(a)).toBe('26 hidden: needs Bounty Pack 3 - A Zane to Kill For')
    expect(hiddenLine(b)).toBe('4 hidden: needs story_pack_1')
    expect(hiddenTotal([a, b])).toBe(30)
  })

  it('formats diff cells', () => {
    expect(formatDiffValue(null)).toBe('—')
    expect(formatDiffValue(60)).toBe('60')
    expect(formatDiffValue(true)).toBe('yes')
    expect(formatDiffValue(['Body', 'Cryo'])).toBe('Body, Cryo')
    expect(formatDiffValue({ a: 1 })).toBe('{"a":1}')
  })

  it('slugs, kinds and titles', () => {
    expect(slugify('Cryo Gravitar!')).toBe('cryo-gravitar')
    expect(slugify('***')).toBe('loadout')
    expect(kindOfType('weapon')).toBe('weapon')
    expect(kindOfType('shield')).toBe('gear')
    expect(kindOfType('', true)).toBe('weapon')
    expect(titleCase('dark_siren')).toBe('Dark Siren')
  })

  it('splits two serials around the changed middle', () => {
    expect(serialDiffParts('@Uabcdef', '@UabXYdef')).toEqual({ prefix: '@Uab', aMid: 'c', bMid: 'XY', suffix: 'def' })
    expect(serialDiffParts('@Uaa', '@Uaa')).toEqual({ prefix: '@Uaa', aMid: '', bMid: '', suffix: '' })
    expect(serialDiffParts('@Uab', '@Uabc')).toEqual({ prefix: '@Uab', aMid: '', bMid: 'c', suffix: '' })
  })

  it('ends server sentences with a stop', () => {
    expect(sentence("run 'bl4forge doctor' for details")).toBe("run 'bl4forge doctor' for details.")
    expect(sentence('done.')).toBe('done.')
    expect(sentence('')).toBe('')
  })
})
