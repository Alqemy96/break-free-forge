import { AlertTriangle, FileCode2, ListPlus, Wand2 } from 'lucide-react'
import { useId, useState } from 'react'
import { ErrorState } from '@/components/item/states'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Field } from '@/components/ui/label'
import { Spinner } from '@/components/ui/misc'
import { NumberField } from '@/components/ui/number-field'
import { useAction } from '@/hooks/useActions'
import { elementKey, kindOfType, plural } from '@/lib/format'
import { parseSpec } from '@/lib/spec'
import { newId } from '@/lib/utils'
import { useApp } from '@/state/app'
import { toast } from '@/state/toast'
import { useTray } from '@/state/trayStore'
import { useBuild } from './buildStore'

const EXAMPLE = `[
  {"group": "Weapons", "query": "wombo combo", "element": "cryo", "display_name": "Wombo Combo"},
  {"group": "Weapons", "type": "shotgun", "element": "radiation"},
  {"group": "Gear", "type": "classmod", "character": "gravitar"},
  {"group": "Gear", "type": "shield", "query": "super soldier"},
  {"group": "Gear", "type": "repkit"}
]`

/** Paste a legacy JSON spec (the cli's --spec file) and build it with server-side search. */
export function QuickBuild() {
  const ids = useId()
  const metaLevel = useApp((s) => s.meta?.level ?? null)
  const [text, setText] = useState('')
  const [title, setTitle] = useState('Quick build')
  const [level, setLevel] = useState<number | null>(metaLevel)
  const [parseError, setParseError] = useState<string | null>(null)
  const [notes, setNotes] = useState<string[]>([])
  const build = useBuild((s) => s.build)
  const status = useBuild((s) => s.status)
  const source = useBuild((s) => s.source)
  const result = useBuild((s) => s.result)
  const error = useBuild((s) => s.error)
  const openSheet = useBuild((s) => s.openSheet)
  const dispatch = useTray((s) => s.dispatch)
  const building = status === 'loading' && source === 'quick'
  const mine = source === 'quick'

  useAction('build', () => void run())

  const run = async () => {
    const parsed = parseSpec(text)
    if (!parsed.ok) {
      setParseError(parsed.error)
      return
    }
    setParseError(null)
    setNotes(parsed.notes)
    const body = level === null ? { requests: parsed.requests, title } : { requests: parsed.requests, title, level }
    const res = await build(body, 'quick')
    if (res && res.loadout.items.length) openSheet()
  }

  const addAll = () => {
    if (!result) return
    for (const it of result.loadout.items) {
      dispatch({
        type: 'add',
        item: {
          id: newId(),
          serial: it.serial,
          name: it.shown_name || it.name,
          label: it.label || it.category || '',
          rarity: it.rarity || null,
          element: elementKey(it.element),
          level: it.level,
          // weapons always carry an element (impact = none); gear has no element at all
          kind: it.type ? kindOfType(it.type) : it.element ? 'weapon' : 'gear',
          group: it.group ?? undefined,
          displayName: it.display_name ?? '',
          note: it.note,
        },
      })
    }
    toast(`Added ${plural(result.loadout.items.length, 'code')} to the tray`, 'ok')
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3">
      <p className="text-[13.5px] text-fg-muted">
        Paste a loadout spec (the cli's <code className="font-mono text-[12.5px] text-fg">--spec</code> JSON). Entries without a{' '}
        <code className="font-mono text-[12.5px] text-fg">serial</code> are searched on the server.
      </p>
      <Field label="Spec (JSON array)" htmlFor={`${ids}-spec`}>
        <Textarea
          id={`${ids}-spec`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={9}
          spellCheck={false}
          placeholder={EXAMPLE}
          aria-invalid={parseError ? true : undefined}
          aria-describedby={parseError ? `${ids}-err` : undefined}
          className="font-mono text-[12px] leading-relaxed"
        />
      </Field>
      {parseError ? (
        <p id={`${ids}-err`} role="alert" className="flex gap-1.5 text-[13px] text-danger">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {parseError}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button size="sm" variant="ghost" onClick={() => setText(EXAMPLE)}>
          <Wand2 /> Load example
        </Button>
      </div>
      <div className="grid grid-cols-[1fr_120px] gap-2">
        <Field label="Title" htmlFor={`${ids}-t`}>
          <Input id={`${ids}-t`} value={title} onChange={(e) => setTitle(e.target.value)} className="h-9 text-[14px]" />
        </Field>
        <Field label="Level" htmlFor={`${ids}-l`}>
          <NumberField id={`${ids}-l`} value={level} min={1} max={100} placeholder="keep" onChange={setLevel} className="h-9" />
        </Field>
      </div>
      <Button variant="primary" onClick={() => void run()} disabled={building || !text.trim()}>
        {building ? <Spinner /> : <FileCode2 />} {building ? 'Building' : 'Build from spec'}
      </Button>

      {mine && error && status === 'error' ? <ErrorState title="Build failed" message={error.message} code={error.code} onRetry={() => void run()} /> : null}

      {mine && result && status === 'ok' ? (
        <div className="flex flex-col gap-2 border border-line bg-surface-2/60 p-3" aria-live="polite">
          <p className="text-[14px] text-fg">
            {plural(result.loadout.items.length, 'item')} resolved
            {result.loadout.unmatched.length ? `, ${result.loadout.unmatched.length} unmatched` : ''}
          </p>
          {result.loadout.unmatched.length ? (
            <div>
              <p className="micro text-danger">Unmatched</p>
              <ul className="mt-1 list-inside list-disc text-[13px] text-fg-muted">
                {result.loadout.unmatched.map((u) => (
                  <li key={u}>{u}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {result.loadout.warnings.length || notes.length ? (
            <div>
              <p className="micro text-warn">Warnings</p>
              <ul className="mt-1 list-inside list-disc text-[13px] text-fg-muted">
                {[...notes, ...result.loadout.warnings].map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2 pt-1">
            <Button size="sm" variant="secondary" onClick={openSheet} disabled={!result.loadout.items.length}>
              <FileCode2 /> Open sheet
            </Button>
            <Button size="sm" variant="outline" onClick={addAll} disabled={!result.loadout.items.length}>
              <ListPlus /> Add all to tray
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
