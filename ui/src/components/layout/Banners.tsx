import { Activity, PlugZap, RotateCw, ServerCrash, TriangleAlert, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import type { ReactNode } from 'react'
import { STATE_LABEL } from '@/components/item/tokens'
import { Button } from '@/components/ui/button'
import { navigate } from '@/hooks/useRoute'
import { sentence } from '@/lib/format'
import { cn } from '@/lib/utils'
import { sickModules, useApp } from '@/state/app'

/** App-wide notices: server unreachable, a module returned 503, or health shows a sick module. */
export function Banners({ screen }: { screen: string }) {
  const offline = useApp((s) => s.offline)
  const unavailable = useApp((s) => s.unavailable)
  const health = useApp((s) => s.health)
  const dismiss = useApp((s) => s.dismissUnavailable)
  const loadMeta = useApp((s) => s.loadMeta)
  const refreshHealth = useApp((s) => s.refreshHealth)
  const sick = sickModules(health)
  const degradedOnly = sick.filter((m) => m.name !== unavailable?.module)

  const retry = () => {
    void loadMeta()
    void refreshHealth()
  }

  return (
    <div className="flex flex-col" role="region" aria-label="Status notices" aria-live="polite">
      <AnimatePresence initial={false}>
        {offline ? (
          <Banner key="offline" tone="danger" icon={<PlugZap className="size-4" />}>
            <span className="font-medium text-fg">Forge server unreachable.</span>{' '}
            <span className="text-fg-muted">
              Start it with <code className="font-mono text-[12.5px] text-fg">bl4forge serve</code> (127.0.0.1:8734) and retry.
            </span>
            <Button size="sm" variant="secondary" className="ml-auto" onClick={retry}>
              <RotateCw /> Retry
            </Button>
          </Banner>
        ) : null}
        {unavailable && !offline ? (
          <Banner key="unavailable" tone="danger" icon={<ServerCrash className="size-4" />}>
            <span className="font-medium text-fg">
              {unavailable.module ? (
                <>
                  Module <code className="font-mono">{unavailable.module}</code> is unavailable.
                </>
              ) : (
                'A module the forge needs is unavailable.'
              )}
            </span>{' '}
            <span className="min-w-0 break-words text-fg-muted">{sentence(unavailable.message)} Other screens keep working.</span>
            <span className="ml-auto flex shrink-0 gap-1">
              {screen !== 'health' ? (
                <Button size="sm" variant="secondary" onClick={() => navigate('health')}>
                  <Activity /> Health
                </Button>
              ) : null}
              <Button size="icon-sm" variant="ghost" aria-label="Dismiss" onClick={dismiss}>
                <X />
              </Button>
            </span>
          </Banner>
        ) : null}
        {!offline && degradedOnly.length && screen !== 'health' ? (
          <Banner key="degraded" tone="warn" icon={<TriangleAlert className="size-4" />}>
            <span className="text-fg-muted">
              {degradedOnly.map((m, i) => (
                <span key={m.name}>
                  {i ? '; ' : ''}
                  <code className="font-mono text-fg">{m.name}</code> is {STATE_LABEL[m.state].toLowerCase()}
                  {m.detail ? ` (${m.detail})` : ''}
                </span>
              ))}
              .{' '}
              {degradedOnly.some((m) => m.state === 'failed' || m.state === 'blocked')
                ? `Features that need ${degradedOnly.length === 1 ? 'it' : 'them'} are unavailable.`
                : `Results that need ${degradedOnly.length === 1 ? 'it' : 'them'} may be incomplete.`}
            </span>
            <Button size="sm" variant="ghost" className="ml-auto" onClick={() => navigate('health')}>
              View health
            </Button>
          </Banner>
        ) : null}
      </AnimatePresence>
    </div>
  )
}

function Banner({ tone, icon, children }: { tone: 'danger' | 'warn'; icon: ReactNode; children: ReactNode }) {
  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: 'auto', opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="overflow-hidden"
    >
      <div
        className={cn(
          'relative flex flex-wrap items-center gap-x-2 gap-y-1 border-b py-2.5 pr-3 pl-6 text-[13.5px]',
          tone === 'danger' ? 'border-danger/40 bg-danger/[0.08]' : 'border-warn/30 bg-warn/[0.06]',
        )}
      >
        <span aria-hidden className={cn('absolute inset-y-0 left-0 w-2', tone === 'danger' ? 'hazard-stripes' : 'hazard-stripes-dim')} />
        <span className={cn('shrink-0', tone === 'danger' ? 'text-danger' : 'text-warn')} aria-hidden>
          {icon}
        </span>
        {children}
      </div>
    </motion.div>
  )
}
