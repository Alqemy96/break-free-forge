import { Activity, Hammer, Keyboard, ScanSearch, type LucideIcon } from 'lucide-react'
import { motion } from 'motion/react'
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
    <nav aria-label="Screens" className="flex w-[76px] shrink-0 flex-col border-r border-line bg-surface-1/70 py-2">
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
                  'relative mx-1.5 flex flex-col items-center gap-1 rounded-[3px] py-2.5 transition-colors',
                  active ? 'bg-surface-3 text-fg' : 'text-fg-dim hover:bg-surface-2 hover:text-fg-muted',
                )}
              >
                {active ? (
                  <motion.span
                    layoutId="nav-indicator"
                    className="absolute top-1.5 bottom-1.5 -left-1.5 w-[3px] bg-hazard shadow-[0_0_12px_var(--color-hazard)]"
                    transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                  />
                ) : null}
                <span className="relative">
                  <Icon className={cn('size-5', active && 'text-hazard')} aria-hidden />
                  {item.id === 'health' && (status === 'degraded' || status === 'down') ? (
                    <span
                      aria-hidden
                      className={cn('absolute -top-0.5 -right-1 size-2 rounded-full ring-2 ring-surface-1', status === 'down' ? 'bg-danger' : 'bg-warn')}
                    />
                  ) : null}
                </span>
                <span className="micro text-[10px]">{item.label}</span>
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
