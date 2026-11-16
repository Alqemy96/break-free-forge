import { Play, RotateCcw, Search } from 'lucide-react'
import { useEffect, useId, useRef, type CSSProperties, type ReactNode, type RefObject } from 'react'
import type { ElementId } from '@/api/types'
import { Magnetic } from '@/components/fx/magnetic'
import { ElementIcon } from '@/components/item/badges'
import { elementColor, rarityColor } from '@/components/item/tokens'
import { Button } from '@/components/ui/button'
import { Chip } from '@/components/ui/chip'
import { Input } from '@/components/ui/input'
import { Field, FieldSet } from '@/components/ui/label'
import { Kbd, SectionLabel, Spinner } from '@/components/ui/misc'
import { NumberField } from '@/components/ui/number-field'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { characterLabel, rarityKey } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useApp } from '@/state/app'
import { defaultForm, type SearchForm } from './form'
import { useForge } from './store'

const FALLBACK_MANUFACTURERS = ['Atlas', 'CoV', 'Daedalus', 'Hyperion', 'Jakobs', 'Maliwan', 'Order', 'Ripper', 'Tediore', 'Torgue', 'Vladof']

export function SearchPanel({
  queryRef,
  manufacturers,
  onRun,
}: {
  queryRef: RefObject<HTMLInputElement | null>
  manufacturers: string[]
  onRun: () => void
}) {
  const ids = useId()
  const meta = useApp((s) => s.meta)
  const form = useForge((s) => s.form)
  const setForm = useForge((s) => s.setForm)
  const replaceForm = useForge((s) => s.replaceForm)
  const status = useForge((s) => s.status)
  const hasRun = useForge((s) => s.ran !== null)
  const timer = useRef<number>(0)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  /** chips/selects re-run automatically once a search has been made; typing waits for Enter */
  const update = (patch: Partial<SearchForm>, auto = true) => {
    setForm(patch)
    if (auto && hasRun) {
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(onRun, 220)
    }
  }
  const toggle = (key: 'type' | 'element' | 'rarity', value: string) => update({ [key]: form[key] === value ? '' : value })

  const types = meta?.types ?? []
  const weaponTypes = types.filter((t) => t.group === 'weapon')
  const gearTypes = types.filter((t) => t.group === 'gear')
  const isClassMod = form.type === 'classmod'
  const manList = manufacturers.length ? manufacturers : FALLBACK_MANUFACTURERS

  return (
    <form
      role="search"
      aria-label="Search the serial catalog"
      onSubmit={(e) => {
        e.preventDefault()
        onRun()
      }}
      className="flex flex-col gap-5"
    >
      <div className="flex items-center justify-between">
        <SectionLabel>Search</SectionLabel>
        <span className="micro hidden text-fg-dim xl:inline">
          <Kbd>/</Kbd> focus
        </span>
      </div>

      <div className="relative">
        <label htmlFor={`${ids}-q`} className="sr-only">
          Item name contains
        </label>
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-fg-dim" />
        <Input
          id={`${ids}-q`}
          ref={queryRef}
          value={form.query}
          onChange={(e) => update({ query: e.target.value }, false)}
          placeholder="Name: crowbar, skeleton key..."
          autoComplete="off"
          spellCheck={false}
          className="h-12 pr-10 pl-9 text-[17px]"
        />
        <Kbd className="absolute top-1/2 right-3 -translate-y-1/2">/</Kbd>
      </div>

      <FieldSet legend="Type" aside={form.type ? <ClearLink onClick={() => update({ type: '' })} /> : null}>
        {types.length === 0 ? (
          <ChipSkeleton count={8} />
        ) : (
          <div className="flex flex-col gap-2">
            <ChipRow label="Weapons">
              {weaponTypes.map((t) => (
                <Chip key={t.id} pressed={form.type === t.id} onClick={() => toggle('type', t.id)}>
                  {t.label}
                </Chip>
              ))}
            </ChipRow>
            <ChipRow label="Gear">
              {gearTypes.map((t) => (
                <Chip key={t.id} pressed={form.type === t.id} color="var(--color-violet-hi)" onClick={() => toggle('type', t.id)}>
                  {t.label}
                </Chip>
              ))}
            </ChipRow>
          </div>
        )}
      </FieldSet>

      <FieldSet legend="Element" aside={form.element ? <ClearLink onClick={() => update({ element: '' })} /> : null}>
        <div className="flex flex-wrap gap-1.5">
          {(meta?.elements ?? []).map((el) => (
            <Chip
              key={el.id}
              pressed={form.element === el.id}
              color={elementColor(el.id as ElementId)}
              icon={<ElementIcon element={el.id as ElementId} className="size-3.5" />}
              onClick={() => toggle('element', el.id)}
            >
              {el.label}
            </Chip>
          ))}
          {!meta ? <ChipSkeleton count={6} /> : null}
        </div>
        {form.element === 'impact' ? <p className="text-[12.5px] text-fg-dim">Impact = no element part (plain kinetic damage).</p> : null}
      </FieldSet>

      <FieldSet legend="Rarity" aside={form.rarity ? <ClearLink onClick={() => update({ rarity: '' })} /> : null}>
        <div className="flex flex-wrap gap-1.5">
          {(meta?.rarities ?? []).map((r) => (
            <Chip key={r} pressed={form.rarity === r} color={rarityColor(rarityKey(r))} onClick={() => toggle('rarity', r)}>
              {r}
            </Chip>
          ))}
          {!meta ? <ChipSkeleton count={7} /> : null}
        </div>
      </FieldSet>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Manufacturer" htmlFor={`${ids}-man`} className="col-span-2 sm:col-span-1 md:col-span-2 2xl:col-span-1">
          <Input
            id={`${ids}-man`}
            list={`${ids}-man-list`}
            value={form.manufacturer}
            onChange={(e) => update({ manufacturer: e.target.value }, false)}
            onBlur={() => hasRun && form.manufacturer !== useForge.getState().ran?.manufacturer && onRun()}
            placeholder="Any"
            autoComplete="off"
          />
          <datalist id={`${ids}-man-list`}>
            {manList.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </Field>
        <Field
          label="Character"
          htmlFor={`${ids}-char`}
          className={cn('col-span-2 sm:col-span-1 md:col-span-2 2xl:col-span-1', isClassMod && 'rounded-[3px] outline outline-1 outline-offset-4 outline-violet/60')}
          hint={isClassMod ? 'Class mods: pick a hunter to see only theirs.' : undefined}
        >
          <Select id={`${ids}-char`} value={form.character} onChange={(e) => update({ character: e.target.value })}>
            <option value="">Any</option>
            {(meta?.characters ?? []).map((c) => (
              <option key={c} value={c}>
                {characterLabel(c)}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Level" htmlFor={`${ids}-lvl`} hint="Results are re-leveled to this. Blank keeps each code's stored level.">
          <NumberField
            id={`${ids}-lvl`}
            value={form.level}
            min={1}
            max={100}
            placeholder="keep"
            onChange={(level) => update({ level }, false)}
          />
        </Field>
        <Field label="Limit" htmlFor={`${ids}-lim`} hint="1 to 200 codes.">
          <NumberField id={`${ids}-lim`} value={form.limit} min={1} max={200} onChange={(n) => update({ limit: n ?? 25 }, false)} />
        </Field>
      </div>

      <div className="flex flex-col gap-4 rounded-[3px] border border-line bg-surface-2/60 p-3">
        <Switch
          id={`${ids}-unowned`}
          checked={form.includeUnowned}
          onCheckedChange={(v) => update({ includeUnowned: v })}
          label="Include unowned content"
          description={
            <>
              Off: codes that need a content pack you do not own
              {meta ? ` (you own ${meta.owned_packs.length})` : ''} are hidden and counted under the results, never dropped silently.
            </>
          }
        />
        <Switch
          id={`${ids}-verify`}
          checked={form.verifyElement}
          onCheckedChange={(v) => update({ verifyElement: v })}
          label="Verify element against the serial"
          description="The database's element label is wrong on some weapons. On: mismatches are dropped and counted."
        />
      </div>

      <div className="flex items-center gap-2">
        <Magnetic className="flex-1">
          <Button type="submit" variant="primary" size="lg" className="w-full" disabled={status === 'loading'}>
            {status === 'loading' ? <Spinner /> : <Play className="fill-current" />}
            {status === 'loading' ? 'Searching' : 'Run search'}
          </Button>
        </Magnetic>
        <Button
          variant="ghost"
          size="icon"
          className="size-12"
          aria-label="Reset filters"
          title="Reset filters"
          onClick={() => replaceForm(defaultForm(meta?.level ?? null))}
        >
          <RotateCcw />
        </Button>
      </div>
      <p className="micro -mt-2 flex items-center gap-1.5 text-fg-dim">
        <Kbd>Ctrl</Kbd>+<Kbd>Enter</Kbd> runs from anywhere on this screen
      </p>
    </form>
  )
}

function ChipRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <span className="micro mt-2 w-14 shrink-0 text-[10px] text-fg-dim">{label}</span>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  )
}

function ClearLink({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="micro text-fg-dim underline-offset-2 hover:text-hazard-hi hover:underline">
      Clear
    </button>
  )
}

function ChipSkeleton({ count }: { count: number }) {
  return (
    <div className="flex flex-wrap gap-1.5" aria-hidden>
      {Array.from({ length: count }, (_, i) => (
        <span key={i} className="skeleton h-8 rounded-[2px]" style={{ width: `${52 + ((i * 17) % 40)}px` } as CSSProperties} />
      ))}
    </div>
  )
}
