import { ArrowDownUp, Dices, Gauge, Replace, ShieldAlert, Sparkles } from 'lucide-react'
import { useId, useState } from 'react'
import type { ElementId, IdentifyResponse } from '@/api/types'
import { ElementIcon } from '@/components/item/badges'
import { ErrorState } from '@/components/item/states'
import { elementColor } from '@/components/item/tokens'
import { Button } from '@/components/ui/button'
import { Chip } from '@/components/ui/chip'
import { Textarea } from '@/components/ui/input'
import { Field } from '@/components/ui/label'
import { Spinner } from '@/components/ui/misc'
import { NumberField } from '@/components/ui/number-field'
import { Switch } from '@/components/ui/switch'
import { panelId, tabId, Tabs } from '@/components/ui/tabs'
import { elementLabel } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useApp } from '@/state/app'
import { useWorkbench } from './store'

type ActionTab = 'relevel' | 'element' | 'reseed' | 'swap'

const SEED_MAX = 2 ** 31 - 1

export function ActionsPanel({
  current,
  positions,
  onPositions,
}: {
  current: IdentifyResponse
  positions: number[]
  onPositions: (positions: number[]) => void
}) {
  const base = useId()
  const [tab, setTab] = useState<ActionTab>('relevel')
  const busy = useWorkbench((s) => s.busy)
  const actionError = useWorkbench((s) => s.actionError)
  const pending = useWorkbench((s) => s.wb.pending)

  return (
    <section className="panel flex flex-col" aria-label="Modify this serial">
      <Tabs
        base={base}
        label="Modify"
        value={tab}
        onChange={setTab}
        items={[
          { id: 'relevel', label: 'Level', icon: <Gauge aria-hidden /> },
          { id: 'element', label: 'Element', icon: <Sparkles aria-hidden /> },
          { id: 'reseed', label: 'Reseed', icon: <Dices aria-hidden /> },
          { id: 'swap', label: 'Swap', icon: <Replace aria-hidden /> },
        ]}
      />
      <div role="tabpanel" id={panelId(base, tab)} aria-labelledby={tabId(base, tab)} className="flex flex-col gap-4 p-4">
        {tab === 'relevel' ? <RelevelForm current={current} /> : null}
        {tab === 'element' ? <ElementForm current={current} /> : null}
        {tab === 'reseed' ? <ReseedForm current={current} /> : null}
        {tab === 'swap' ? <SwapForm current={current} positions={positions} onPositions={onPositions} /> : null}
        {actionError && !busy ? <ErrorState title="Refused" message={actionError.message} code={actionError.code} /> : null}
        {pending ? (
          <p className="micro text-hazard-hi">A result is waiting below: use it or discard it before the next change.</p>
        ) : null}
      </div>
    </section>
  )
}

function RunButton({ op, label, disabled, onClick }: { op: string; label: string; disabled?: boolean; onClick: () => void }) {
  const busy = useWorkbench((s) => s.busy)
  const pending = useWorkbench((s) => s.wb.pending)
  return (
    <Button variant="primary" onClick={onClick} disabled={disabled || busy !== null || pending !== null} className="self-start">
      {busy === op ? <Spinner /> : null}
      {label}
    </Button>
  )
}

function RelevelForm({ current }: { current: IdentifyResponse }) {
  const id = useId()
  const metaLevel = useApp((s) => s.meta?.level ?? 60)
  const [level, setLevel] = useState<number | null>(current.info.level === metaLevel ? 50 : metaLevel)
  const transform = useWorkbench((s) => s.transform)
  return (
    <>
      <Field label="New level" htmlFor={id} hint={`Currently Lv ${current.info.level ?? '?'}. Same parts, same seed.`}>
        <div className="flex flex-wrap items-center gap-2">
          <NumberField id={id} value={level} min={1} max={100} onChange={setLevel} className="w-36" />
          {[30, 50, metaLevel].filter((v, i, a) => a.indexOf(v) === i).map((v) => (
            <Chip key={v} pressed={level === v} onClick={() => setLevel(v)}>
              Lv {v}
            </Chip>
          ))}
        </div>
      </Field>
      <RunButton
        op="relevel"
        label="Re-level"
        disabled={level === null || level === current.info.level}
        onClick={() => level !== null && transform({ serial: current.serial, op: 'relevel', level }, `re-level to ${level}`)}
      />
    </>
  )
}

function ElementForm({ current }: { current: IdentifyResponse }) {
  const meta = useApp((s) => s.meta)
  const transform = useWorkbench((s) => s.transform)
  const [element, setElement] = useState<ElementId | null>(null)
  const allowed = current.can_set_element
  const now = current.info.element ?? 'impact'
  const elements = meta?.elements ?? []
  return (
    <>
      {!allowed ? (
        <p className="flex gap-2 border border-line bg-surface-2 px-3 py-2 text-[13.5px] text-fg-muted">
          <ShieldAlert className="mt-0.5 size-4 shrink-0 text-fg-dim" aria-hidden />
          Only weapons carry an element part. This item is gear, so its element cannot be set.
        </p>
      ) : (
        <p className="text-[13.5px] text-fg-muted">
          Now: <span className="text-fg">{elementLabel(now)}</span>. Impact strips the element part (plain kinetic damage).
        </p>
      )}
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Target element">
        {elements.map((el) => (
          <Chip
            key={el.id}
            pressed={element === el.id}
            disabled={!allowed || el.id === now}
            color={elementColor(el.id)}
            icon={<ElementIcon element={el.id} className="size-3.5" />}
            onClick={() => setElement(el.id)}
            className={cn((!allowed || el.id === now) && 'cursor-not-allowed opacity-40')}
          >
            {el.id === 'impact' ? 'Impact (strip)' : el.label}
          </Chip>
        ))}
      </div>
      <RunButton
        op="set_element"
        label={element ? `Set ${elementLabel(element)}` : 'Set element'}
        disabled={!allowed || element === null}
        onClick={() =>
          element &&
          transform(
            { serial: current.serial, op: 'set_element', element },
            element === 'impact' ? 'strip element (impact)' : `set element ${elementLabel(element).toLowerCase()}`,
          )
        }
      />
    </>
  )
}

function ReseedForm({ current }: { current: IdentifyResponse }) {
  const id = useId()
  const [seed, setSeed] = useState<number | null>(null)
  const transform = useWorkbench((s) => s.transform)
  return (
    <>
      <Field label="Seed (optional)" htmlFor={id} hint="Rerolls stat variance; parts and level stay. Blank = a random seed.">
        <NumberField id={id} value={seed} min={0} max={SEED_MAX} placeholder="random" onChange={setSeed} className="w-48" />
      </Field>
      <RunButton
        op="reseed"
        label="Reseed"
        onClick={() =>
          transform(
            seed === null ? { serial: current.serial, op: 'reseed' } : { serial: current.serial, op: 'reseed', seed },
            seed === null ? 'reseed (random)' : `reseed ${seed}`,
          )
        }
      />
    </>
  )
}

function SwapForm({
  current,
  positions,
  onPositions,
}: {
  current: IdentifyResponse
  positions: number[]
  onPositions: (positions: number[]) => void
}) {
  const id = useId()
  const [text, setText] = useState('')
  const [allowCross, setAllowCross] = useState(false)
  const source = useWorkbench((s) => s.source)
  const sourceLoading = useWorkbench((s) => s.sourceLoading)
  const sourceError = useWorkbench((s) => s.sourceError)
  const loadSource = useWorkbench((s) => s.loadSource)
  const transform = useWorkbench((s) => s.transform)

  const cross = source !== null && source.info.category_id !== current.info.category_id
  const toggle = (pos: number) =>
    onPositions(positions.includes(pos) ? positions.filter((p) => p !== pos) : [...positions, pos].sort((a, b) => a - b))

  return (
    <>
      <p className="text-[13.5px] text-fg-muted">
        Copy parts from a second serial into this one. Positions are the numbers in the parts list; the part at the same
        position is replaced.
      </p>
      <Field label="Source serial" htmlFor={id}>
        <div className="flex flex-col gap-2">
          <Textarea
            id={id}
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={2}
            spellCheck={false}
            placeholder="@U..."
            className="min-h-0 font-mono text-[12.5px]"
          />
          <Button size="sm" variant="secondary" className="self-start" onClick={() => loadSource(text)} disabled={!text.trim() || sourceLoading}>
            {sourceLoading ? <Spinner /> : <ArrowDownUp />} Load source parts
          </Button>
        </div>
      </Field>
      {sourceError ? <ErrorState title="Source not readable" message={sourceError.message} code={sourceError.code} /> : null}

      {source ? (
        <>
          <p className="text-[13px] text-fg-muted">
            Source: <span className="text-fg">{source.info.display_name ?? source.info.category ?? 'item'}</span> /{' '}
            {source.info.category} ({source.info.category_id})
          </p>
          {cross ? (
            <div className="flex flex-col gap-3 border border-danger/45 bg-danger/[0.07] p-3">
              <p className="flex gap-2 text-[13.5px] text-fg">
                <ShieldAlert className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
                Different item categories ({current.info.category} vs {source.info.category}). Part numbers are
                category-relative, so a copied part would decode as something unrelated. The server refuses this unless you
                allow it.
              </p>
              <Switch
                id={`${id}-cross`}
                tone="danger"
                checked={allowCross}
                onCheckedChange={setAllowCross}
                label="Allow cross-category swap"
                description="Only if you know both categories share a parts table."
              />
            </div>
          ) : null}
          <fieldset className="m-0 border-0 p-0">
            <legend className="micro mb-2 text-fg-muted">Positions to copy ({positions.length} picked)</legend>
            <ul className="flex max-h-72 flex-col overflow-y-auto border border-line">
              {source.parts.map((p) => {
                const mine = current.parts[p.position]
                const checked = positions.includes(p.position)
                const same = mine?.label === p.label
                return (
                  <li key={p.position} className="border-b border-line/60 last:border-b-0">
                    <label
                      className={cn(
                        'flex cursor-pointer items-start gap-2.5 px-3 py-1.5 text-[13px] transition-colors',
                        checked ? 'bg-hazard/10' : 'hover:bg-surface-2',
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggle(p.position)}
                        className="mt-1 size-3.5 accent-[var(--color-hazard)]"
                      />
                      <span className="w-6 shrink-0 font-mono text-[12px] text-fg-dim">{p.position}</span>
                      <span className="min-w-0 flex-1">
                        <span className="text-fg">{p.label}</span>
                        <span className="block text-[12px] text-fg-dim">
                          {mine ? (same ? 'same as this item' : `replaces ${mine.label}`) : 'no part at this position here'}
                        </span>
                      </span>
                    </label>
                  </li>
                )
              })}
            </ul>
          </fieldset>
          <RunButton
            op="swap"
            label={`Swap ${positions.length || ''} part${positions.length === 1 ? '' : 's'}`}
            disabled={positions.length === 0 || (cross && !allowCross)}
            onClick={() =>
              transform(
                { serial: current.serial, op: 'swap', source: source.serial, positions, allow_cross: cross && allowCross },
                `swap position${positions.length === 1 ? '' : 's'} ${positions.join(', ')}`,
              )
            }
          />
          <p className="text-[12.5px] text-fg-dim">
            A swapped item has passed structural checks only; part compatibility is not verified.
          </p>
        </>
      ) : null}
    </>
  )
}
