import { ScanSearch, Wrench } from 'lucide-react'
import { AnimatePresence } from 'motion/react'
import { useEffect, useId, useRef, useState } from 'react'
import { EmptyState, ErrorState } from '@/components/item/states'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { Kbd, SectionLabel, Skeleton, Spinner } from '@/components/ui/misc'
import { NumberField } from '@/components/ui/number-field'
import { useAction } from '@/hooks/useActions'
import { navigate, useRoute } from '@/hooks/useRoute'
import { currentEntry } from '@/state/workbench'
import { ActionsPanel } from './ActionsPanel'
import { Dossier } from './Dossier'
import { HistoryStack } from './HistoryStack'
import { PendingResult } from './PendingResult'
import { useWorkbench } from './store'

export function WorkbenchScreen() {
  const ids = useId()
  const route = useRoute()
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const input = useWorkbench((s) => s.input)
  const setInput = useWorkbench((s) => s.setInput)
  const identify = useWorkbench((s) => s.identify)
  const identifying = useWorkbench((s) => s.identifying)
  const identifyError = useWorkbench((s) => s.identifyError)
  const wb = useWorkbench((s) => s.wb)
  const [atLevel, setAtLevel] = useState<number | null>(null)
  const [positions, setPositions] = useState<number[]>([])

  const current = currentEntry(wb)
  const serialParam = route.params.serial

  const run = () => {
    const serial = (inputRef.current?.value ?? input).trim()
    if (!serial) {
      inputRef.current?.focus()
      return
    }
    navigate('workbench', { serial }, true)
    void identify(serial, atLevel ?? undefined)
  }
  useAction('run', run)
  useAction('focusSearch', () => inputRef.current?.focus())

  // arrive with ?serial=... (Inspect from the forge, or a reload)
  useEffect(() => {
    if (!serialParam) return
    const st = useWorkbench.getState()
    const cur = currentEntry(st.wb)
    if (cur?.payload.serial === serialParam || st.identifying) return
    st.setInput(serialParam)
    void st.identify(serialParam)
  }, [serialParam])

  // keep the hash pointing at the current serial (so a reload restores it)
  useEffect(() => {
    // not while a new serial is being identified (it would briefly point the hash back)
    if (current && !useWorkbench.getState().identifying && current.payload.serial !== serialParam) {
      navigate('workbench', { serial: current.payload.serial }, true)
    }
    setPositions([])
  }, [current?.payload.serial])

  return (
    <div className="flex min-h-full flex-col gap-5 p-4 lg:p-6">
      <h1 className="sr-only">Workbench: inspect and modify a serial</h1>
      <section className="panel p-4" aria-labelledby={`${ids}-h`}>
        <div className="mb-3 flex items-center justify-between gap-3">
          <SectionLabel>
            <span id={`${ids}-h`}>Workbench / inspect a serial</span>
          </SectionLabel>
          <span className="micro hidden text-fg-dim sm:inline">
            <Kbd>Ctrl</Kbd>+<Kbd>Enter</Kbd> identify
          </span>
        </div>
        <form
          className="grid gap-3 md:grid-cols-[minmax(0,1fr)_150px_auto] md:items-end"
          onSubmit={(e) => {
            e.preventDefault()
            run()
          }}
        >
          <div className="flex min-w-0 flex-col gap-1.5">
            <label htmlFor={`${ids}-serial`} className="micro text-fg-muted">
              Serial
            </label>
            <Textarea
              id={`${ids}-serial`}
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
                  e.preventDefault()
                  run()
                }
              }}
              rows={2}
              spellCheck={false}
              autoComplete="off"
              placeholder="Paste a code: @Uge(J0Fnkb..."
              aria-invalid={identifyError ? true : undefined}
              className="min-h-[52px] resize-y font-mono text-[13.5px]"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${ids}-lvl`} className="micro text-fg-muted">
              At level <span className="text-fg-dim">(optional)</span>
            </label>
            <NumberField id={`${ids}-lvl`} value={atLevel} min={1} max={100} placeholder="as is" onChange={setAtLevel} />
          </div>
          <Button type="submit" variant="primary" size="lg" disabled={identifying} className="h-[52px]">
            {identifying ? <Spinner /> : <ScanSearch />} Identify
          </Button>
        </form>
        <p className="sr-only" aria-live="polite">
          {identifying ? 'Identifying' : current ? `Identified ${current.payload.info.display_name ?? 'item'}` : ''}
        </p>
      </section>

      {identifyError && !identifying ? (
        <ErrorState title="Could not identify" message={identifyError.message} code={identifyError.code} onRetry={run} art="ai-ally" />
      ) : null}

      {identifying && !current ? <DossierSkeleton /> : null}

      {!current && !identifying && !identifyError ? (
        <EmptyState icon={Wrench} title="Bench is empty" art="takeover">
          <p>
            Paste any serial to see what it really is: name, rarity, element, level, drop odds (base rates) and every part by
            position. Or press <span className="text-fg">Inspect</span> on a search result.
          </p>
        </EmptyState>
      ) : null}

      {current ? (
        <div className={identifying ? 'grid gap-5 opacity-60 transition-opacity xl:grid-cols-[minmax(0,1fr)_380px]' : 'grid gap-5 transition-opacity xl:grid-cols-[minmax(0,1fr)_380px]'}>
          <Dossier payload={current.payload} marked={positions} />
          <div className="flex min-w-0 flex-col gap-4">
            <ActionsPanel current={current.payload} positions={positions} onPositions={setPositions} />
            <AnimatePresence mode="wait">{wb.pending ? <PendingResult key={wb.pending.result.serial} pending={wb.pending} /> : null}</AnimatePresence>
            <HistoryStack />
            <Button variant="ghost" size="sm" className="self-start" onClick={() => navigate('forge')}>
              Back to the forge
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function DossierSkeleton() {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]" aria-hidden>
      <div className="flex flex-col gap-4">
        <div className="panel p-5">
          <Skeleton className="h-3 w-40" />
          <Skeleton className="mt-3 h-12 w-2/3" />
          <Skeleton className="mt-4 h-5 w-1/2" />
          <Skeleton className="mt-5 h-10 w-full" />
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
      <Skeleton className="h-80 w-full" />
    </div>
  )
}
