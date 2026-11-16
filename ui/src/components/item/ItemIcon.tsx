import { useId, type CSSProperties, type ReactNode } from 'react'
import type { ElementId } from '@/api/types'
import { elementKey, rarityKey } from '@/lib/format'
import { ICON_LABEL, type IconKind } from '@/lib/itemKind'
import { cn } from '@/lib/utils'
import { elementColor, rarityColor } from './tokens'

/**
 * Original ink-style item silhouettes (plain SVG shapes drawn for this project; nothing traced from
 * any game or manufacturer). The body takes `currentColor` (set from the rarity token), outlines are
 * black, the shade and highlight are neutral overlays, so one path set recolours per rarity.
 */

const INK = { stroke: '#000', strokeWidth: 3, strokeLinejoin: 'round', strokeLinecap: 'round' } as const

function Shade({ d }: { d: string }) {
  return <path d={d} fill="#000" fillOpacity={0.3} stroke="none" />
}
function Shine({ d }: { d: string }) {
  return <path d={d} fill="none" stroke="#fff" strokeOpacity={0.45} strokeWidth={2} strokeLinecap="round" />
}

const SHAPES: Record<IconKind, ReactNode> = {
  pistol: (
    <>
      <path {...INK} fill="currentColor" d="M6 16h72l9 5h25v15H88l-6 5H66l-4 22H46l4-22H28l-5-4H6z" />
      <Shade d="M30 16h34v8H30z" />
      <Shine d="M10 20h62" />
      <circle cx="96" cy="28" r="3" fill="#000" />
    </>
  ),
  smg: (
    <>
      <path {...INK} fill="currentColor" d="M4 22h22l5-5h50l8 5h26v12h-24l-6 6H68l-3 4h-8l-2 18H44l3-18H32l-5-5H4z" />
      <path {...INK} fill="currentColor" d="M72 38h12l4 24H76z" />
      <Shade d="M34 17h44v8H34z" />
      <Shine d="M10 25h62" />
      <circle cx="108" cy="28" r="3" fill="#000" />
    </>
  ),
  shotgun: (
    <>
      <path {...INK} fill="currentColor" d="M3 32l16-6h30l12-4h58v9H65v5H50l-9 11H28l-6 13-13-3 9-18-9-4z" />
      <path {...INK} fill="currentColor" d="M64 38h24v6H64z" />
      <Shade d="M22 27h32v6H22z" />
      <Shine d="M24 28h82" />
      <circle cx="112" cy="26" r="2.5" fill="#000" />
    </>
  ),
  assault_rifle: (
    <>
      <path {...INK} fill="currentColor" d="M3 26h14l5-5h32l4-5h14l4 5h38v10H86l-5 5H66l-3 4h-6l-3 18H40l3-18H30l-5 5H11l-4-6z" />
      <path {...INK} fill="currentColor" d="M44 14h14v5H44z" />
      <Shade d="M24 21h36v7H24z" />
      <Shine d="M24 24h72" />
      <circle cx="110" cy="31" r="2.5" fill="#000" />
    </>
  ),
  sniper: (
    <>
      <path {...INK} fill="currentColor" d="M3 30l12-3h24l5-4h44l8 3h22v7H96l-6 4H60l-6 4h-6l-3 14H34l3-14-6-3H15z" />
      <path {...INK} fill="currentColor" d="M34 11h38v9H34z" />
      <Shade d="M36 13h34v3H36z" />
      <Shine d="M46 26h60" />
      <circle cx="40" cy="15.5" r="2" fill="#000" />
    </>
  ),
  heavy: (
    <>
      <path {...INK} fill="currentColor" d="M4 24h14v-4h50v4h22v26H68v-3H48l-4 18H30l4-18H20l-4-4H4z" />
      <path {...INK} fill="currentColor" d="M90 18h24v38H90z" />
      <Shade d="M94 22h16v6H94z" />
      <Shine d="M10 27h54" />
      <circle cx="102" cy="42" r="6" fill="#000" />
    </>
  ),
  shield: (
    <>
      <path {...INK} fill="currentColor" d="M60 4l42 10v22c0 16-18 27-42 33C36 63 18 52 18 36V14z" />
      <path d="M60 4l42 10v22c0 16-18 27-42 33z" fill="#000" fillOpacity={0.3} />
      <path {...INK} fill="none" strokeWidth={2.5} d="M60 14v46M34 24l26 6 26-6" />
      <Shine d="M26 18l30-8" />
    </>
  ),
  grenade: (
    <>
      <circle {...INK} cx="58" cy="44" r="22" fill="currentColor" />
      <path d="M58 22a22 22 0 0 1 0 44z" fill="#000" fillOpacity={0.3} />
      <path {...INK} fill="currentColor" d="M48 10h20v10H48z" />
      <path {...INK} fill="currentColor" d="M68 12h20l6 8H70z" />
      <circle {...INK} cx="94" cy="14" r="6" fill="none" />
      <path {...INK} fill="none" strokeWidth={2.5} d="M40 34l36 20M40 54l36-20" />
      <Shine d="M42 30a18 18 0 0 1 8-6" />
    </>
  ),
  classmod: (
    <>
      <path {...INK} fill="currentColor" d="M36 10h48l14 14v26L84 64H36L22 50V24z" />
      <path d="M60 10h24l14 14v26L84 64H60z" fill="#000" fillOpacity={0.3} />
      <path {...INK} fill="none" strokeWidth={2.5} d="M4 24h18M4 36h18M4 48h18M98 24h18M98 36h18M98 48h18" />
      <path {...INK} fill="#000" fillOpacity={0.55} strokeWidth={2} d="M60 22l16 15-16 15-16-15z" />
      <Shine d="M38 15h40" />
    </>
  ),
  repkit: (
    <>
      <path {...INK} fill="currentColor" d="M18 22h84v40H18z" />
      <path {...INK} fill="currentColor" d="M44 10h32v12H44z" />
      <path d="M60 22h42v40H60z" fill="#000" fillOpacity={0.3} />
      <path {...INK} fill="#07080b" strokeWidth={2.5} d="M53 30h14v9h9v14h-9v9H53v-9h-9V39h9z" transform="translate(0 -4) scale(1 .85) translate(0 8)" />
      <Shine d="M22 26h40" />
    </>
  ),
  enhancement: (
    <>
      <path {...INK} fill="currentColor" d="M60 4l44 17v30L60 68 16 51V21z" />
      <path d="M60 4l44 17v30L60 68z" fill="#000" fillOpacity={0.3} />
      <path {...INK} fill="#07080b" strokeWidth={2.5} d="M60 18l20 20H68v18H52V38H40z" />
      <Shine d="M22 24l34-14" />
    </>
  ),
  unknown: (
    <>
      <path {...INK} fill="currentColor" d="M16 22l44-14 44 14v38L60 68 16 60z" />
      <path d="M60 8l44 14v38L60 68z" fill="#000" fillOpacity={0.3} />
      <path {...INK} fill="none" strokeWidth={2.5} d="M16 22l44 14 44-14M60 36v32" />
      <path {...INK} fill="#07080b" strokeWidth={2} d="M52 44a8 8 0 1 1 11 7c-2 1-3 2-3 4v2" />
      <circle cx="60" cy="63" r="1.6" fill="#07080b" />
    </>
  ),
}

/** Element glyphs: 16x16, bold simple shapes, generic (flame, bolt, snowflake, drop, trefoil, burst). */
const GLYPHS: Record<ElementId, ReactNode> = {
  fire: <path d="M8 1c1 3 5 5 5 9a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 2 2 2-1-3 0-5 1-7z" />,
  shock: <path d="M9 1L3 9h4l-1 6 7-9H9z" />,
  cryo: <path d="M8 1v14M2 4.5l12 7M2 11.5l12-7M6 2l2 2 2-2M6 14l2-2 2 2" fill="none" strokeWidth={1.8} strokeLinecap="round" />,
  corrosive: <path d="M8 1C5 6 3 8 3 10.5a5 5 0 0 0 10 0C13 8 11 6 8 1z" />,
  radiation: (
    <>
      <path d="M8 8L5 2.8A6 6 0 0 1 11 2.8z" />
      <path d="M8 8l6 .1A6 6 0 0 1 11 13.2z" />
      <path d="M8 8L5 13.2A6 6 0 0 1 2 8.1z" />
      <circle cx="8" cy="8" r="1.4" />
    </>
  ),
  impact: <path d="M8 1l2 4.5L15 6l-3.5 3.3L12.5 14 8 11.6 3.5 14l1-4.7L1 6l5-.5z" />,
}

export function ElementGlyph({ element, className, title }: { element: ElementId | string | null | undefined; className?: string; title?: string }) {
  const key = elementKey(element)
  if (!key) return null
  return (
    <svg viewBox="0 0 16 16" className={cn('size-4 shrink-0', className)} style={{ color: elementColor(key) }} role={title ? 'img' : undefined} aria-hidden={title ? undefined : true}>
      {title ? <title>{title}</title> : null}
      <g fill="currentColor" stroke="currentColor" strokeWidth={0.4} strokeLinejoin="round">
        {GLYPHS[key]}
      </g>
    </svg>
  )
}

/** Generic maker slot: a small shape picked deterministically from the maker name. Never a real logo. */
const MAKER_SHAPES: ReactNode[] = [
  <circle key="c" cx="8" cy="8" r="6" />,
  <path key="t" d="M8 2l7 12H1z" />,
  <rect key="s" x="2.5" y="2.5" width="11" height="11" />,
  <path key="d" d="M8 1l7 7-7 7-7-7z" />,
  <path key="h" d="M4.5 2h7l4 6-4 6h-7l-4-6z" />,
  <path key="x" d="M6 1h4v5h5v4h-5v5H6v-5H1V6h5z" />,
  <path key="v" d="M1 3h5l2 5 2-5h5l-7 11z" />,
  <path key="b" d="M1 3h14v3H1zM1 10h14v3H1z" />,
]

function hashString(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619)
  return h >>> 0
}

export function MakerMark({ maker, className }: { maker: string | null | undefined; className?: string }) {
  const name = (maker ?? '').trim()
  if (!name) return null
  const shape = MAKER_SHAPES[hashString(name.toLowerCase()) % MAKER_SHAPES.length]
  return (
    <svg viewBox="0 0 16 16" className={cn('size-4 shrink-0 text-fg-muted', className)} aria-hidden>
      <title>{`Maker: ${name}`}</title>
      <g fill="currentColor" stroke="#000" strokeWidth={1.2} strokeLinejoin="round">
        {shape}
      </g>
    </svg>
  )
}

export interface ItemIconProps {
  kind: IconKind
  rarity?: string | null
  element?: ElementId | string | null
  maker?: string | null
  className?: string
  /** decorative (the card text already names the item): the default */
  label?: string
  /** draw the element glyph and maker mark in the corners (off for tiny icons) */
  marks?: boolean
}

/**
 * The item silhouette, recoloured by rarity, with an optional element glyph and maker mark pinned to
 * the corners. Size comes from the parent (fills its width, 5:3).
 */
export function ItemIcon({ kind, rarity, element, maker, className, label, marks = true }: ItemIconProps) {
  const id = useId()
  const rKey = rarityKey(rarity)
  const style = { color: rarityColor(rKey) } as CSSProperties
  return (
    <div className={cn('relative aspect-[5/3] w-full', className)} style={style} data-icon={kind}>
      <svg
        viewBox="0 0 120 72"
        className="absolute inset-0 size-full drop-shadow-[0_0_10px_color-mix(in_oklab,currentColor_35%,transparent)]"
        role="img"
        aria-labelledby={label ? id : undefined}
        aria-hidden={label ? undefined : true}
        preserveAspectRatio="xMidYMid meet"
      >
        {label ? <title id={id}>{label}</title> : null}
        {SHAPES[kind]}
      </svg>
      {marks ? (
        <>
          <ElementGlyph element={element} className="absolute right-0 bottom-0 size-[18%] min-h-4 min-w-4" />
          <MakerMark maker={maker} className="absolute bottom-0 left-0 size-[16%] min-h-4 min-w-4" />
        </>
      ) : null}
    </div>
  )
}

export { ICON_LABEL }
