import { HelpCircle, Link2 } from 'lucide-react'
import type { IdentifyPart } from '@/api/types'
import { cn } from '@/lib/utils'

/**
 * The numbered parts list. `position` is what swap uses. Unknown parts (no manifest name) and
 * category links are highlighted; positions picked for a swap are marked.
 */
export function PartsTable({
  parts,
  marked = [],
  caption = 'Parts',
}: {
  parts: IdentifyPart[]
  marked?: number[]
  caption?: string
}) {
  const unknown = parts.filter((p) => p.raw === null && p.category_link === null).length
  const links = parts.filter((p) => p.category_link !== null).length
  return (
    <div className="min-w-0">
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        <p className="micro text-fg-muted">
          {caption} <span className="text-fg-dim">({parts.length})</span>
        </p>
        {unknown ? (
          <p className="micro flex items-center gap-1 text-warn">
            <HelpCircle className="size-3" aria-hidden /> {unknown} unknown
          </p>
        ) : null}
        {links ? (
          <p className="micro flex items-center gap-1 text-violet-hi">
            <Link2 className="size-3" aria-hidden /> {links} category {links === 1 ? 'link' : 'links'}
          </p>
        ) : null}
      </div>
      <div className="overflow-x-auto border border-line">
        <table className="w-full border-collapse text-left text-[13.5px]">
          <caption className="sr-only">{caption}: position, part name, manifest id, category and index</caption>
          <thead className="bg-surface-2">
            <tr className="micro text-fg-dim">
              <th scope="col" className="w-12 px-3 py-2 font-normal">Pos</th>
              <th scope="col" className="px-3 py-2 font-normal">Part</th>
              <th scope="col" className="hidden px-3 py-2 font-normal md:table-cell">Manifest id</th>
              <th scope="col" className="w-24 px-3 py-2 text-right font-normal">Cat:Idx</th>
            </tr>
          </thead>
          <tbody>
            {parts.map((p) => {
              const isUnknown = p.raw === null && p.category_link === null
              const isLink = p.category_link !== null
              const isMarked = marked.includes(p.position)
              return (
                <tr
                  key={`${p.position}-${p.token_index}`}
                  className={cn(
                    'border-t border-line/70 transition-colors',
                    isMarked ? 'bg-hazard/10' : 'hover:bg-surface-2/70',
                    isUnknown && !isMarked && 'bg-warn/[0.05]',
                  )}
                >
                  <td className="px-3 py-1.5 font-mono text-[12.5px] text-fg-muted">
                    <span className={cn('inline-block min-w-6 text-center', isMarked && 'rounded-[2px] bg-hazard px-1 font-semibold text-hazard-ink')}>
                      {p.position}
                    </span>
                  </td>
                  <td className="px-3 py-1.5">
                    <span className={cn('text-fg', isUnknown && 'text-warn', isLink && 'text-violet-hi')}>
                      {isUnknown ? <HelpCircle className="mr-1.5 inline size-3.5 align-[-2px]" aria-hidden /> : null}
                      {isLink ? <Link2 className="mr-1.5 inline size-3.5 align-[-2px]" aria-hidden /> : null}
                      {p.label}
                    </span>
                    {isLink ? <span className="ml-2 font-mono text-[11.5px] text-violet-hi/80">links category {p.category_link}</span> : null}
                    {isUnknown ? <span className="ml-2 text-[12px] text-warn/90">not in the manifest</span> : null}
                  </td>
                  <td className="hidden px-3 py-1.5 font-mono text-[12px] text-fg-dim md:table-cell">{p.raw ?? '—'}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-[12px] text-fg-dim">
                    {p.category_id ?? '—'}:{p.index}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
