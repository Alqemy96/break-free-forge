import { AlertTriangle, Dice5, Lock, Plus, ShieldCheck, ShieldAlert, Check } from 'lucide-react'
import type { CSSProperties } from 'react'
import type { IdentifyResponse } from '@/api/types'
import { CopyButton } from '@/components/fx/copy-button'
import { TextScramble } from '@/components/fx/text-scramble'
import { ElementBadge, RarityBadge } from '@/components/item/badges'
import { SerialText } from '@/components/item/serial'
import { rarityColor } from '@/components/item/tokens'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { rarityKey } from '@/lib/format'
import { newId } from '@/lib/utils'
import { toast } from '@/state/toast'
import { useTray } from '@/state/trayStore'
import { PartsTable } from './PartsTable'

export function Dossier({ payload, marked }: { payload: IdentifyResponse; marked: number[] }) {
  const { info } = payload
  const rKey = rarityKey(info.rarity)
  const name = info.display_name || info.legendary_name || info.category || 'Unknown item'
  const inTray = useTray((s) => s.tray.items.some((it) => it.serial === payload.serial))
  const dispatch = useTray((s) => s.dispatch)

  const addToTray = () => {
    dispatch({
      type: 'add',
      item: {
        id: newId(),
        serial: payload.serial,
        name,
        label: info.category ?? '',
        rarity: info.rarity,
        element: info.element,
        level: info.level,
        kind: payload.is_weapon ? 'weapon' : 'gear',
      },
    })
    toast(`Added ${name} to the loadout`, 'ok')
  }

  return (
    <article className="flex min-w-0 flex-col gap-5" aria-labelledby="dossier-name" style={{ '--spot': rarityColor(rKey) } as CSSProperties}>
      <header className="panel relative overflow-hidden p-5">
        <span aria-hidden className="absolute inset-y-0 left-0 w-1" style={{ background: 'var(--spot)', boxShadow: '0 0 18px var(--spot)' }} />
        <span
          aria-hidden
          className="pointer-events-none absolute -top-24 -right-24 size-72 rounded-full opacity-25 blur-3xl"
          style={{ background: 'var(--spot)' }}
        />
        <p className="micro text-fg-dim">{info.category ?? 'Unknown category'} / category {info.category_id ?? '?'}</p>
        <h2 id="dossier-name" className="title-display mt-1 text-[clamp(34px,4.6vw,56px)] text-fg">
          <TextScramble text={name} duration={0.7} trigger={payload.serial} />
        </h2>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <RarityBadge rarity={info.rarity} />
          <ElementBadge element={info.element} showNone={!payload.is_weapon} />
          <Badge>Lv {info.level ?? '?'}</Badge>
          <Badge>{payload.is_weapon ? 'Weapon' : 'Gear'}</Badge>
          <Badge tone={info.owned ? 'neutral' : 'violet'}>
            {info.owned ? null : <Lock aria-hidden />}
            {info.content_pack_label || info.content_pack}
            {info.owned ? ' / owned' : ' / not owned'}
          </Badge>
          {!info.manifest_ok ? <Badge tone="warn">manifest incomplete</Badge> : null}
        </div>
        {info.other_components.length ? (
          <p className="mt-3 text-[13.5px] text-fg-muted">
            Also carries:{' '}
            {info.other_components.map(([rarity, compName], i) => (
              <span key={`${rarity}-${i}`}>
                {i ? ', ' : ''}
                {rarity} {compName ?? 'component'}
              </span>
            ))}
            <span className="text-fg-dim"> (the highest tier governs)</span>
          </p>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-2 rounded-[2px] border border-line bg-bg/60 p-2 pl-3">
          <SerialText serial={payload.serial} full className="min-w-0 flex-1 text-[13px]" />
          <div className="flex shrink-0 gap-2">
            <CopyButton text={payload.serial} what={`${name} code`} />
            <Button size="sm" variant={inTray ? 'secondary' : 'outline'} onClick={addToTray} disabled={inTray}>
              {inTray ? <Check /> : <Plus />} {inTray ? 'In loadout' : 'Add to loadout'}
            </Button>
          </div>
        </div>
      </header>

      <div className="grid gap-3 md:grid-cols-2">
        <section className="panel p-4" aria-labelledby="odds-h">
          <h3 id="odds-h" className="micro flex items-center gap-1.5 text-fg-muted">
            <Dice5 className="size-3.5 text-hazard" aria-hidden /> Drop odds <span className="text-fg-dim">(base rates)</span>
          </h3>
          <p className="mt-2 font-mono text-[13px] leading-relaxed text-warn">{payload.odds || 'No drop data for this item.'}</p>
          <p className="mt-2 text-[12.5px] text-fg-dim">Luck and event modifiers are not in the data.</p>
        </section>
        <section className="panel p-4" aria-labelledby="struct-h">
          <h3 id="struct-h" className="micro flex items-center gap-1.5 text-fg-muted">
            {payload.problems.length ? (
              <ShieldAlert className="size-3.5 text-danger" aria-hidden />
            ) : (
              <ShieldCheck className="size-3.5 text-ok" aria-hidden />
            )}
            Structure
          </h3>
          {payload.problems.length ? (
            <ul className="mt-2 flex flex-col gap-1 text-[13.5px] text-danger">
              {payload.problems.map((p) => (
                <li key={p} className="flex gap-1.5">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                  <span className="break-words">{p}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-[14px] text-ok">Passed structural checks.</p>
          )}
          <p className="mt-2 text-[12.5px] text-fg-dim">Structural checks only: not a guarantee the item is valid in game.</p>
        </section>
      </div>

      {info.warnings.length ? (
        <ul className="flex flex-col gap-1 border border-warn/35 bg-warn/[0.06] px-4 py-3 text-[13.5px] text-warn">
          {info.warnings.map((w) => (
            <li key={w} className="flex gap-1.5">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              <span className="break-words">{w}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <PartsTable parts={payload.parts} marked={marked} caption="Parts (position = swap number)" />

      <details className="group border border-line bg-surface-1/60">
        <summary className="micro px-4 py-2.5 text-fg-dim hover:text-fg">Raw tokens</summary>
        <pre className="overflow-x-auto px-4 pb-4 font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-all text-fg-muted">{info.tokens}</pre>
      </details>
    </article>
  )
}
