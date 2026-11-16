import { Activity, Hammer, Keyboard, ScanSearch, type LucideIcon } from 'lucide-react'
import { formToHash } from '@/features/forge/form'
import { useForge } from '@/features/forge/store'
import { useWorkbench } from '@/features/workbench/store'
import { buildHash, type Screen } from '@/lib/route'
import { cn } from '@/lib/utils'
import { overallStatus, useApp } from '@/state/app'
import { currentEntry } from '@/state/workbench'

const ITEMS: { id: Screen; label: string; icon: LucideIcon; key: string }[] = [
  { id: 'forge', label: 'Forge', icon: Hammer, key: '1' },
  { id: 'workbench', label: 'Bench', icon: ScanSearch, key: '2' },
  { id: 'health', label: 'Health', icon: Activity, key: '3' },
]

export function NavRail({ screen, onShortcuts }: { screen: Screen; onShortcuts: () => void }) {
  const ran = useForge((s) => s.ran)
  const serial = useWorkbench((s) => currentEntry(s.wb)?.payload.serial ?? null)
  const status = useApp((s) => overallStatus(s.health, s.offline))

  const hrefFor = (id: Screen) =>
    id === 'forge' && ran ? buildHash('forge', formToHash(ran)) : id === 'workbench' && serial ? buildHash('workbench', { serial }) : buildHash(id)

  return (
    <nav aria-label="Screens" className="flex w-[84px] shrink-0 flex-col border-r-2 border-line bg-[#050609] py-3">
      <ul className="flex flex-col gap-1">
        {ITEMS.map((item) => {
          const active = item.id === screen
          const Icon = item.icon
          return (
            <li key={item.id}>
              <a
                href={hrefFor(item.id)}
                aria-current={active ? 'page' : undefined}
                title={`${item.label} (${item.key})`}
                className={cn(
                  'glitch relative mx-1.5 flex flex-col items-center gap-1 rounded-[2px] border-2 py-2.5 transition-colors',
                  active ? 'border-black bg-hazard text-hazard-ink shadow-[3px_3px_0_var(--color-pink)]' : 'border-transparent text-fg-muted hover:bg-surface-2 hover:text-fg',
                )}
              >
                <span className="relative">
                  <Icon className="size-5" aria-hidden />
                  {item.id === 'health' && (status === 'degraded' || status === 'down') ? (
                    <span
                      aria-hidden
                      className={cn('absolute -top-0.5 -right-1 size-2 rounded-full ring-2 ring-black', status === 'down' ? 'bg-danger' : 'bg-warn')}
                    />
                  ) : null}
                </span>
                <span className="micro text-[11px]">{item.label}</span>
              </a>
            </li>
          )
        })}
      </ul>
      <button
        type="button"
        onClick={onShortcuts}
        className="mx-1.5 mt-auto flex flex-col items-center gap-1 rounded-[3px] py-2.5 text-fg-dim hover:bg-surface-2 hover:text-fg-muted"
        aria-label="Keyboard shortcuts (?)"
        title="Keyboard shortcuts (?)"
      >
        <Keyboard className="size-5" aria-hidden />
        <span className="micro text-[10px]">Keys</span>
      </button>
    </nav>
  )
}
