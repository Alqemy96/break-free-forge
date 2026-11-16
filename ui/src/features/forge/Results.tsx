import { AlertTriangle, EyeOff, Info, Lock, PackageSearch, SearchX, Sparkles } from 'lucide-react'
import { motion } from 'motion/react'
import { AnimatedGroup } from '@/components/fx/animated-group'
import { NumberTicker } from '@/components/fx/number-ticker'
import { EmptyState, ErrorState } from '@/components/item/states'
import { Button } from '@/components/ui/button'
import { SectionLabel } from '@/components/ui/misc'
import { elementLabel, hiddenLine, hiddenTotal, plural } from '@/lib/format'
import type { SearchForm } from './form'
import { ItemCard, ItemCardSkeleton } from './ItemCard'
import { useForge } from './store'

const QUICK_PICKS: { label: string; patch: Partial<SearchForm> }[] = [
  { label: 'Anarchy', patch: { query: 'anarchy' } },
  { label: 'Cryo shotguns', patch: { type: 'shotgun', element: 'cryo' } },
  { label: 'Gravitar class mods', patch: { type: 'classmod', character: 'gravitar' } },
  { label: 'Legendary shields', patch: { type: 'shield', rarity: 'Legendary' } },
  { label: 'Shock SMGs', patch: { type: 'smg', element: 'shock' } },
]

export function Results({ onRun }: { onRun: () => void }) {
  const status = useForge((s) => s.status)
  const data = useForge((s) => s.data)
  const error = useForge((s) => s.error)
  const ran = useForge((s) => s.ran)
  const runId = useForge((s) => s.runId)
  const setForm = useForge((s) => s.setForm)

  const pick = (patch: Partial<SearchForm>) => {
    setForm({ query: '', type: '', element: '', rarity: '', character: '', manufacturer: '', ...patch })
    onRun()
  }

  const summary =
    status === 'loading'
      ? 'Searching the catalog'
      : status === 'error'
        ? `Search failed: ${error?.message ?? ''}`
        : data
          ? `${plural(data.count, 'result')}${data.level !== null ? `, re-leveled to ${data.level}` : ', stored levels'}${data.hidden.length ? `, ${hiddenTotal(data.hidden)} hidden` : ''}`
          : ''

  return (
    <section aria-labelledby="results-heading" className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line pb-3">
        <div className="flex items-end gap-4">
          <SectionLabel as="h2">
            <span id="results-heading">Results</span>
          </SectionLabel>
          {data ? (
            <p className="flex items-baseline gap-2">
              <NumberTicker value={data.count} className="title-display text-[34px] leading-none text-fg" />
              <span className="micro text-fg-dim">
                {data.count === 1 ? 'code' : 'codes'}
                {data.level !== null ? ` / Lv ${data.level}` : ' / stored levels'}
              </span>
            </p>
          ) : null}
        </div>
        {data && ran && data.count >= ran.limit ? (
          <p className="micro text-fg-dim">First {ran.limit} shown. Raise the limit (max 200) for more.</p>
        ) : null}
      </div>
      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {summary}
      </p>

      {status === 'loading' ? (
        <motion.div
          aria-hidden
          className="hazard-stripes h-[3px] w-full origin-left"
          initial={{ scaleX: 0 }}
          animate={{ scaleX: [0, 0.6, 0.9] }}
          transition={{ duration: 1.6, ease: 'easeOut' }}
        />
      ) : null}

      {status === 'error' && error ? <ErrorState title="Search failed" message={error.message} code={error.code} onRetry={onRun} /> : null}

      {data && status !== 'error' ? <Notices onRun={onRun} /> : null}

      {status === 'idle' && !data ? (
        <EmptyState icon={PackageSearch} title="The locker is closed" className="mt-2">
          <p>
            Pick a type, an element or a rarity, or type part of a name, then run the search. Every code is checked against its
            own bitstream before it is shown.
          </p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {QUICK_PICKS.map((q) => (
              <Button key={q.label} size="sm" variant="outline" onClick={() => pick(q.patch)}>
                <Sparkles /> {q.label}
              </Button>
            ))}
          </div>
        </EmptyState>
      ) : null}

      {status === 'loading' && !data ? (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(270px,1fr))] gap-3" aria-label="Loading results">
          {Array.from({ length: 6 }, (_, i) => (
            <ItemCardSkeleton key={i} />
          ))}
        </ul>
      ) : null}

      {data && data.count === 0 && status !== 'error' ? (
        <EmptyState icon={SearchX} title="Nothing matched">
          <p>
            No code passed every filter{ran?.element ? ` (element ${elementLabel(ran.element)})` : ''}. Clear a filter or try a
            shorter name.
            {data.hidden.length ? ' Some matches are hidden because they need content you do not own (see above).' : ''}
          </p>
        </EmptyState>
      ) : null}

      {data && data.count > 0 ? (
        <div className={status === 'loading' ? 'pointer-events-none opacity-50 transition-opacity' : 'transition-opacity'}>
          <AnimatedGroup key={runId} label="Search results" className="grid grid-cols-[repeat(auto-fill,minmax(270px,1fr))] gap-3">
            {data.results.map((row, i) => (
              <ItemCard key={row.serial} row={row} index={i} />
            ))}
          </AnimatedGroup>
        </div>
      ) : null}
    </section>
  )
}

function Notices({ onRun }: { onRun: () => void }) {
  const data = useForge((s) => s.data)
  const ran = useForge((s) => s.ran)
  const setForm = useForge((s) => s.setForm)
  if (!data) return null
  const total = hiddenTotal(data.hidden)
  const showAll = () => {
    setForm({ includeUnowned: true })
    onRun()
  }
  const notices = []
  if (data.hidden.length) {
    notices.push(
      <div key="hidden" className="flex flex-wrap items-center gap-3 border border-violet/40 bg-violet-deep/40 px-4 py-3">
        <Lock className="size-4 shrink-0 text-violet-hi" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-medium text-fg">
            {plural(total, 'match', 'matches')} hidden: {total === 1 ? 'it needs' : 'they need'} content you do not own
          </p>
          <ul className="mt-0.5 text-[13px] text-violet-hi">
            {data.hidden.map((h) => (
              <li key={h.pack}>{hiddenLine(h)}</li>
            ))}
          </ul>
        </div>
        <Button size="sm" variant="violet" onClick={showAll}>
          <EyeOff /> Include unowned?
        </Button>
      </div>,
    )
  }
  if (data.dropped_element_mismatch > 0) {
    notices.push(
      <div key="dropped" className="flex items-start gap-3 border border-warn/35 bg-warn/[0.06] px-4 py-3 text-[14px]">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
        <p className="text-fg-muted">
          <span className="font-medium text-fg">{plural(data.dropped_element_mismatch, 'code')} dropped:</span> the database labels{' '}
          {data.dropped_element_mismatch === 1 ? 'it' : 'them'} {elementLabel(ran?.element)}, but the serial decodes to a different
          element. Turn off "Verify element" to see database labels unchecked.
        </p>
      </div>,
    )
  }
  for (const note of data.notes ?? []) {
    notices.push(
      <p key={`note-${note}`} className="flex items-center gap-2 text-[13px] text-fg-muted">
        <Info className="size-3.5 shrink-0 text-violet-hi" aria-hidden />
        <span>
          <span className="micro mr-1.5 text-violet-hi">Server note</span>
          {note}
        </span>
      </p>,
    )
  }
  if (ran && !ran.verifyElement) {
    notices.push(
      <p key="noverify" className="micro text-warn">
        Element verification is off: element filters use database labels, which are wrong on some weapons.
      </p>,
    )
  }
  return notices.length ? <div className="flex flex-col gap-2">{notices}</div> : null
}
