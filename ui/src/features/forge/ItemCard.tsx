import { AlertTriangle, Check, Lock, Plus, ScanSearch } from 'lucide-react'
import { motion } from 'motion/react'
import type { CSSProperties } from 'react'
import type { SearchResultRow } from '@/api/types'
import { groupItem } from '@/components/fx/animated-group'
import { CopyButton } from '@/components/fx/copy-button'
import { trackSpotlight } from '@/components/fx/spotlight'
import { TextScramble } from '@/components/fx/text-scramble'
import { ElementBadge, RarityBadge } from '@/components/item/badges'
import { ItemIcon } from '@/components/item/ItemIcon'
import { SerialText } from '@/components/item/serial'
import { rarityColor } from '@/components/item/tokens'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip } from '@/components/ui/tooltip'
import { navigate } from '@/hooks/useRoute'
import { elementKey, elementLabel, kindOfType, rarityKey } from '@/lib/format'
import { iconKindOf } from '@/lib/itemKind'
import { cn, newId } from '@/lib/utils'
import { toast } from '@/state/toast'
import { useTray } from '@/state/trayStore'

export function ItemCard({ row, index }: { row: SearchResultRow; index: number }) {
  const inTray = useTray((s) => s.tray.items.find((it) => it.serial === row.serial)?.id ?? null)
  const dispatch = useTray((s) => s.dispatch)

  const decoded = row.decoded
  const rarity = decoded.rarity ?? row.rarity
  const rKey = rarityKey(rarity)
  const element = decoded.element
  const hintElement = elementKey(row.element)
  const elementDisagrees = hintElement !== null && element !== null && hintElement !== element
  const warnings = [...decoded.warnings, ...(row.warnings ?? [])]
  const decodesAs = decoded.display_name && !row.name.toLowerCase().includes(decoded.display_name.toLowerCase()) ? decoded.display_name : null
  const icon = iconKindOf({ type: row.type, weaponType: row.weapon_type, category: decoded.category })
  const high = rKey === 'legendary' || rKey === 'pearl' || rKey === 'vile'

  const toggleTray = () => {
    if (inTray) {
      dispatch({ type: 'remove', id: inTray })
      toast(`Removed ${row.name} from the loadout`, 'info')
      return
    }
    dispatch({
      type: 'add',
      item: {
        id: newId(),
        serial: row.serial,
        name: row.name,
        label: row.label,
        rarity,
        element,
        level: row.level,
        kind: kindOfType(row.type),
        icon,
        maker: row.manufacturer || undefined,
      },
    })
    toast(`Added ${row.name} to the loadout`, 'ok')
  }

  return (
    <motion.li variants={groupItem} custom={index} className="list-none">
      <article
        onPointerMove={trackSpotlight}
        style={{ '--spot': rarityColor(rKey), '--edge': `color-mix(in oklab, ${rarityColor(rKey)} 55%, var(--color-line))` } as CSSProperties}
        className="spotlight panel ink-edge group/card relative flex h-full flex-col gap-3 p-4"
        aria-labelledby={`card-${index}-name`}
      >
        <span aria-hidden className="spotlight-ring" />
        <div
          className={cn('relative -mx-4 -mt-4 border-b-2 border-black px-4 pt-3 pb-2', high && 'shadow-[inset_0_-14px_24px_-18px_var(--spot)]')}
          style={{ background: 'radial-gradient(circle at 75% 25%, color-mix(in oklab, var(--spot) 22%, transparent), transparent 62%), #08090d' }}
        >
          <span aria-hidden className="absolute inset-0 opacity-[0.22]" style={{ backgroundImage: 'radial-gradient(circle, var(--spot) 1.4px, transparent 1.9px)', backgroundSize: '9px 9px', maskImage: 'linear-gradient(200deg, #000, transparent 62%)', WebkitMaskImage: 'linear-gradient(200deg, #000, transparent 62%)' }} />
          <ItemIcon kind={icon} rarity={rarity} element={element} maker={row.manufacturer} className="mx-auto max-w-[220px]" />
          <span className="absolute top-2 right-2 border-2 border-[color:var(--spot)] bg-black px-1.5 font-display text-[14px] leading-6 text-fg">L{row.level ?? '?'}</span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 pr-3">
          <RarityBadge rarity={rarity} />
          <ElementBadge element={element} />
          {decoded.owned === false ? (
            <Badge tone="violet">
              <Lock aria-hidden /> Not owned
            </Badge>
          ) : null}
        </div>

        <div className="min-w-0">
          <h3 id={`card-${index}-name`} className="title-display text-[21px] leading-[1.05] text-fg">
            <TextScramble text={row.name} duration={0.55} delay={index * 0.035} disabled={index >= 12} />
          </h3>
          <p className="mt-1 truncate text-[13.5px] text-fg-muted" title={row.label}>
            <span className="font-mono text-[12px] text-fg">Lv {row.level ?? '?'}</span>
            <span aria-hidden className="px-1.5 text-fg-dim">/</span>
            {row.label || row.manufacturer || row.type}
            {decodesAs ? (
              <>
                <span aria-hidden className="px-1.5 text-fg-dim">/</span>
                <span className="text-fg-dim">decodes as</span> {decodesAs}
              </>
            ) : null}
          </p>
        </div>

        {elementDisagrees || warnings.length > 0 ? (
          <ul className="flex flex-col gap-1 text-[12.5px] leading-snug text-warn">
            {elementDisagrees ? (
              <li className="flex gap-1.5">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                Database says {elementLabel(hintElement)}; the serial decodes as {elementLabel(element)}.
              </li>
            ) : null}
            {warnings.map((w) => (
              <li key={w} className="flex gap-1.5">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                <span className="min-w-0 break-words">{w}</span>
              </li>
            ))}
          </ul>
        ) : null}

        <div className="mt-auto flex items-center gap-2 rounded-[2px] border border-line bg-bg/60 py-1 pr-1 pl-2.5">
          <SerialText serial={row.serial} className="min-w-0 flex-1 truncate" />
          <CopyButton text={row.serial} compact variant="ghost" what={`${row.name} code`} />
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            className="px-2"
            onClick={() => navigate('workbench', { serial: row.serial })}
            aria-label={`Inspect ${row.name} in the workbench`}
          >
            <ScanSearch /> Inspect
          </Button>
          <Tooltip content={inTray ? 'Already in the loadout. Click to take it out.' : 'Add this exact code to the loadout tray.'} side="top">
            {(p) => (
              <Button
                size="sm"
                variant={inTray ? 'secondary' : 'outline'}
                className={cn('ml-auto', inTray && 'border-ok/50 text-ok')}
                onClick={toggleTray}
                aria-pressed={Boolean(inTray)}
                {...p}
              >
                {inTray ? <Check /> : <Plus />}
                {inTray ? 'In loadout' : 'Loadout'}
              </Button>
            )}
          </Tooltip>
        </div>
      </article>
    </motion.li>
  )
}

export function ItemCardSkeleton() {
  return (
    <li className="panel list-none p-4 pt-5" aria-hidden="true">
      <div className="flex gap-1.5">
        <div className="skeleton h-5 w-20 rounded-[2px]" />
        <div className="skeleton h-5 w-14 rounded-[2px]" />
      </div>
      <div className="skeleton mt-4 h-6 w-3/4 rounded-[2px]" />
      <div className="skeleton mt-2 h-4 w-1/2 rounded-[2px]" />
      <div className="skeleton mt-6 h-9 w-full rounded-[2px]" />
      <div className="mt-3 flex justify-between">
        <div className="skeleton h-8 w-20 rounded-[2px]" />
        <div className="skeleton h-8 w-24 rounded-[2px]" />
      </div>
    </li>
  )
}
