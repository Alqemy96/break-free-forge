import { Tooltip } from '@/components/ui/tooltip'
import { STATE_LABEL } from '@/components/item/tokens'
import { navigate } from '@/hooks/useRoute'
import { cn } from '@/lib/utils'
import { overallStatus, sickModules, useApp } from '@/state/app'

const COLORS = {
  ok: 'bg-ok',
  degraded: 'bg-warn',
  down: 'bg-danger',
  unknown: 'bg-fg-dim',
} as const

/** Compact module-health dot: green when all 7 cells are OK, amber/red otherwise. */
export function StatusDot() {
  const health = useApp((s) => s.health)
  const offline = useApp((s) => s.offline)
  const status = overallStatus(health, offline)
  const sick = sickModules(health)
  const label =
    status === 'ok'
      ? `All ${health?.modules.length ?? 7} modules OK`
      : status === 'unknown'
        ? 'Module health not checked yet'
        : offline
          ? 'Server unreachable'
          : `${sick.length} module${sick.length === 1 ? '' : 's'} not OK`

  return (
    <Tooltip
      content={
        <span className="flex flex-col gap-1">
          <span className="font-medium">{label}</span>
          {sick.map((m) => (
            <span key={m.name} className="font-mono text-[12px] text-fg-muted">
              {m.name}: {STATE_LABEL[m.state].toLowerCase()}
              {m.detail ? ` (${m.detail})` : ''}
            </span>
          ))}
          <span className="text-[11.5px] text-fg-dim">Click for the health mesh</span>
        </span>
      }
    >
      {(p) => (
        <button
          type="button"
          onClick={() => navigate('health')}
          aria-label={`Module health: ${label}. Open the health screen.`}
          className="relative grid size-9 place-items-center rounded-[3px] border border-line bg-surface-2 hover:border-line-strong"
          {...p}
        >
          <span className={cn('relative size-2.5 rounded-full', COLORS[status])}>
            {status !== 'ok' && status !== 'unknown' ? (
              <span className={cn('absolute inset-0 animate-ping rounded-full opacity-70', COLORS[status])} />
            ) : null}
          </span>
        </button>
      )}
    </Tooltip>
  )
}
