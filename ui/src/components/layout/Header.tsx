import { Boxes } from 'lucide-react'
import { MaskLogo } from '@/components/brand/MaskLogo'
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
    <header className="relative z-30 flex h-16 shrink-0 items-center gap-4 border-b-[3px] border-hazard bg-black pr-3 pl-4 shadow-[0_6px_0_var(--color-pink)]">
      <a
        href="#/forge"
        className="group flex items-center gap-3 rounded-[2px]"
        onPointerEnter={() => setReplay((n) => n + 1)}
        aria-label="Break Free Forge, go to the forge"
      >
        <MaskLogo className="size-10 shrink-0" />
        <span className="flex flex-col">
          <TextScramble text="BREAK FREE FORGE" trigger={replay} duration={0.6} className="title-display text-[22px] leading-none tracking-[0.04em] whitespace-nowrap text-fg" />
          <span className="mt-1 hidden text-[12.5px] whitespace-nowrap text-fg-muted md:block">You bought it. You should be able to open it.</span>
        </span>
      </a>
      

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
              'glitch relative inline-flex h-9 items-center gap-2 rounded-[2px] border-2 px-3 font-display text-[14px] uppercase tracking-[0.06em] transition-colors',
              trayOpen ? 'border-black bg-hazard text-hazard-ink shadow-[3px_3px_0_var(--color-pink)]' : 'border-line-strong bg-surface-3 text-fg hover:border-fg-dim',
            )}
            {...p}
          >
            <Boxes className="size-4" aria-hidden />
            <span className="hidden sm:inline">Loadout</span>
            <span
              className={cn(
                'grid h-5 min-w-5 place-items-center rounded-[2px] px-1 font-mono text-[11.5px] font-semibold',
                count ? (trayOpen ? 'bg-black text-hazard' : 'bg-hazard text-hazard-ink') : 'bg-surface-4 text-fg-dim',
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
