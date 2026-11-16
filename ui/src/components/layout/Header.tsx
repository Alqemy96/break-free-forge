import { Boxes } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { isMock } from '@/api'
import { NumberTicker } from '@/components/fx/number-ticker'
import { TextScramble } from '@/components/fx/text-scramble'
import { Badge } from '@/components/ui/badge'
import { Kbd, Skeleton } from '@/components/ui/misc'
import { Tooltip } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useApp } from '@/state/app'
import { useTray } from '@/state/trayStore'
import { TRAY_ID } from '@/features/loadout/TrayDrawer'
import { StatusDot } from './StatusDot'

export function Header() {
  const meta = useApp((s) => s.meta)
  const trayOpen = useApp((s) => s.trayOpen)
  const setTrayOpen = useApp((s) => s.setTrayOpen)
  const count = useTray((s) => s.tray.items.length)
  const [replay, setReplay] = useState(0)

  return (
    <header className="relative z-30 flex h-14 shrink-0 items-center gap-4 border-b border-line bg-surface-1/95 pr-3 pl-4 shadow-[0_1px_0_rgb(255_255_255/0.03)]">
      <a
        href="#/forge"
        className="group flex items-center gap-3 rounded-[2px]"
        onPointerEnter={() => setReplay((n) => n + 1)}
        aria-label="BL4 Forge, go to the forge"
      >
        <Mark />
        <span className="flex flex-col">
          <TextScramble text="BL4 FORGE" trigger={replay} duration={0.6} className="title-display text-[25px] leading-none tracking-[0.04em] whitespace-nowrap text-fg" />
          <span className="micro mt-0.5 hidden text-[9.5px] tracking-[0.2em] whitespace-nowrap text-fg-dim md:block">Loadout forge // local</span>
        </span>
      </a>
      <span aria-hidden className="hazard-stripes hidden h-6 w-12 -skew-x-12 opacity-60 lg:block" />

      <dl className="ml-auto flex items-center gap-5">
        <Stat label="Catalog" className="hidden sm:flex">
          {meta && meta.catalog_count === null ? (
            <span className="font-mono text-[14px] text-danger" title="The catalog module is unavailable">
              offline
            </span>
          ) : meta ? (
            <span className="flex items-baseline gap-1">
              <NumberTicker value={meta.catalog_count ?? 0} className="font-mono text-[14px] text-fg" />
              <span className="text-[12px] text-fg-dim">codes</span>
            </span>
          ) : (
            <Skeleton className="h-4 w-20" />
          )}
        </Stat>
        <Stat label="Manifest" className="hidden lg:flex">
          {meta ? (
            <span className="block max-w-[220px] truncate font-mono text-[12.5px] text-fg-muted" title={meta.manifest_version ?? 'data module unavailable'}>
              {meta.manifest_version ?? 'unavailable'}
            </span>
          ) : (
            <Skeleton className="h-4 w-28" />
          )}
        </Stat>
        <Stat label="Level" className="hidden md:flex">
          {meta ? <span className="font-mono text-[14px] text-fg">{meta.level}</span> : <Skeleton className="h-4 w-6" />}
        </Stat>
      </dl>

      {isMock ? (
        <Badge tone="violet" title="VITE_MOCK=1: in-memory fixtures, no server">
          Mock data
        </Badge>
      ) : null}
      <StatusDot />

      <Tooltip content={<span className="flex items-center gap-2">Loadout tray <Kbd>L</Kbd></span>}>
        {(p) => (
          <button
            type="button"
            onClick={() => setTrayOpen(!trayOpen)}
            aria-expanded={trayOpen}
            aria-controls={TRAY_ID}
            className={cn(
              'relative inline-flex h-9 items-center gap-2 rounded-[3px] border px-3 font-display text-[15px] font-semibold uppercase tracking-[0.06em] transition-colors',
              trayOpen ? 'border-hazard bg-hazard/15 text-hazard-hi' : 'border-line-strong bg-surface-3 text-fg hover:border-fg-dim',
            )}
            {...p}
          >
            <Boxes className="size-4" aria-hidden />
            <span className="hidden sm:inline">Loadout</span>
            <span
              className={cn(
                'grid h-5 min-w-5 place-items-center rounded-[2px] px-1 font-mono text-[11.5px] font-semibold',
                count ? 'bg-hazard text-hazard-ink' : 'bg-surface-4 text-fg-dim',
              )}
            >
              <NumberTicker value={count} />
              <span className="sr-only"> items</span>
            </span>
          </button>
        )}
      </Tooltip>
    </header>
  )
}

function Stat({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex-col items-start', className)}>
      <dt className="micro text-[9.5px] text-fg-dim">{label}</dt>
      <dd className="m-0">{children}</dd>
    </div>
  )
}

/** The mark: a hazard triangle plate. */
function Mark() {
  return (
    <svg viewBox="0 0 32 32" className="size-8 shrink-0" aria-hidden>
      <rect x="0.5" y="0.5" width="31" height="31" rx="2" fill="var(--color-surface-3)" stroke="var(--color-line-strong)" />
      <path d="M6 24 L16 6 L26 24 Z" fill="none" stroke="var(--color-hazard)" strokeWidth="2.6" />
      <rect x="14.6" y="12.5" width="2.8" height="6.4" fill="var(--color-hazard)" />
      <rect x="14.6" y="20.2" width="2.8" height="2.6" fill="var(--color-hazard)" />
    </svg>
  )
}
