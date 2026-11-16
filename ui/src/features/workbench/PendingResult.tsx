import { ArrowDown, Check, Info, X } from 'lucide-react'
import { motion } from 'motion/react'
import type { DiffRow } from '@/api/types'
import { CopyButton } from '@/components/fx/copy-button'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/misc'
import { formatDiffValue, serialDiffParts } from '@/lib/format'
import type { PendingTransform } from '@/state/workbench'
import { useWorkbench } from './store'

/** Before/after for a proposed transform, with the field diff from /api/diff. */
export function PendingResult({ pending }: { pending: PendingTransform }) {
  const dispatch = useWorkbench((s) => s.dispatch)
  const { result } = pending
  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 6 }}
      transition={{ type: 'spring', stiffness: 420, damping: 34 }}
      className="relative overflow-hidden border border-hazard/60 bg-surface-1"
      aria-labelledby="pending-h"
    >
      <div aria-hidden className="hazard-stripes h-1.5 w-full opacity-80" />
      <div className="flex flex-col gap-4 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 id="pending-h" className="title-display text-[22px] text-fg">
            Proposed: <span className="text-hazard-hi">{pending.label}</span>
          </h3>
          <p className="micro text-fg-dim">Not applied yet</p>
        </div>

        <SerialDiff before={result.previous} after={result.serial} />

        <DiffTable rows={pending.diff} error={pending.diffError} />

        {result.note ? (
          <p className="flex gap-2 text-[13px] text-fg-muted">
            <Info className="mt-0.5 size-4 shrink-0 text-violet-hi" aria-hidden />
            {result.note}
          </p>
        ) : null}
        {result.problems.length ? (
          <ul className="text-[13px] text-danger">
            {result.problems.map((p) => (
              <li key={p}>Structural problem: {p}</li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-ok">Passed structural checks (not a guarantee the item is valid in game).</p>
        )}

        <div className="flex flex-wrap gap-2">
          <Button variant="primary" onClick={() => dispatch({ type: 'accept' })}>
            <Check /> Use this
          </Button>
          <CopyButton text={result.serial} label="Copy new code" what="New code" />
          <Button variant="ghost" onClick={() => dispatch({ type: 'discard' })} className="ml-auto">
            <X /> Discard
          </Button>
        </div>
      </div>
    </motion.section>
  )
}

export function DiffTable({ rows, error }: { rows: DiffRow[] | null; error: string | null }) {
  if (rows === null) {
    return (
      <div className="flex flex-col gap-1.5" aria-label="Loading the diff">
        <Skeleton className="h-7 w-full" />
        <Skeleton className="h-7 w-5/6" />
      </div>
    )
  }
  if (error) return <p className="text-[13px] text-warn">Could not load the diff: {error}</p>
  if (rows.length === 0) return <p className="text-[13px] text-fg-muted">No decoded field changed (the bitstream differs only in the seed/stat variance).</p>
  return (
    <div className="overflow-x-auto border border-line">
      <table className="w-full border-collapse text-left text-[13px]">
        <caption className="sr-only">What changed</caption>
        <thead className="bg-surface-2">
          <tr className="micro text-fg-dim">
            <th scope="col" className="px-3 py-1.5 font-normal">Field</th>
            <th scope="col" className="px-3 py-1.5 font-normal">Before</th>
            <th scope="col" className="px-3 py-1.5 font-normal">After</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.field} className="border-t border-line/70">
              <th scope="row" className="px-3 py-1.5 font-mono text-[12px] font-normal text-fg-muted">
                {r.field}
              </th>
              <td className="px-3 py-1.5 text-danger/90 line-through decoration-danger/50">{formatDiffValue(r.a)}</td>
              <td className="px-3 py-1.5 font-medium text-ok">{formatDiffValue(r.b)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Both serials in full, with the changed characters marked (del/ins, not colour alone). */
export function SerialDiff({ before, after }: { before: string; after: string }) {
  const { prefix, aMid, bMid, suffix } = serialDiffParts(before, after)
  const shared = 'text-fg-dim'
  return (
    <div className="flex flex-col gap-1.5 font-mono text-[12px] leading-relaxed">
      <div className="border border-line bg-bg/60 px-3 py-2">
        <p className="micro mb-1 text-fg-dim">Before</p>
        <code className="break-all">
          <span className={shared}>{prefix}</span>
          {aMid ? <del className="bg-danger/20 text-danger decoration-danger/60">{aMid}</del> : null}
          <span className={shared}>{suffix}</span>
        </code>
      </div>
      <ArrowDown className="mx-auto size-4 text-hazard" aria-hidden />
      <div className="border border-hazard/40 bg-hazard/[0.05] px-3 py-2">
        <p className="micro mb-1 text-hazard-hi">After</p>
        <code className="break-all">
          <span className={shared}>{prefix}</span>
          {bMid ? <ins className="bg-ok/20 text-ok no-underline">{bMid}</ins> : null}
          <span className={shared}>{suffix}</span>
        </code>
      </div>
    </div>
  )
}
