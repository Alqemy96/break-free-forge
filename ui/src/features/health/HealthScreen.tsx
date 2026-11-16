import { Activity, CheckCircle2, CircleDashed, RefreshCw, XCircle } from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import type { ModuleRow } from '@/api/types'
import { NumberTicker } from '@/components/fx/number-ticker'
import { EmptyState, ErrorState } from '@/components/item/states'
import { STATE_COLOR, STATE_LABEL } from '@/components/item/tokens'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { SectionLabel, Skeleton, Spinner } from '@/components/ui/misc'
import { Switch } from '@/components/ui/switch'
import { useAction } from '@/hooks/useActions'
import { cn } from '@/lib/utils'
import { sickModules, useApp } from '@/state/app'
import { MeshDiagram, OUTER } from './MeshDiagram'

const AUTO_MS = 15000

export function HealthScreen() {
  const ids = useId()
  const health = useApp((s) => s.health)
  const healthError = useApp((s) => s.healthError)
  const loading = useApp((s) => s.healthLoading)
  const at = useApp((s) => s.healthAt)
  const refresh = useApp((s) => s.refreshHealth)
  const [auto, setAuto] = useState(false)
  const [hover, setHover] = useState<string | null>(null)
  const [pinned, setPinned] = useState<string | null>(null)

  useAction('run', () => void refresh())

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (!auto) return
    const t = window.setInterval(() => void refresh(), AUTO_MS)
    return () => window.clearInterval(t)
  }, [auto, refresh])

  const modules = health?.modules ?? []
  const healthy = modules.filter((m) => m.state === 'ok' && m.contract_problems.length === 0).length
  const sick = sickModules(health)
  const focus = hover ?? pinned
  const shown = modules.find((m) => m.name === focus) ?? modules.find((m) => m.name === pinned) ?? sick[0] ?? modules[0] ?? null

  return (
    <div className="flex min-h-full flex-col gap-5 p-4 lg:p-6">
      <h1 className="sr-only">Module health</h1>
      <section className="panel ink-edge flex flex-wrap items-end justify-between gap-4 p-5" aria-labelledby={`${ids}-h`}>
        <div>
          <SectionLabel>
            <span id={`${ids}-h`}>Health / the module mesh</span>
          </SectionLabel>
          <p className="mt-2 flex items-baseline gap-3">
            {health ? (
              <>
                <span className={cn('title-display text-[56px] leading-none', sick.some((m) => m.state === 'failed' || m.state === 'blocked') ? 'text-danger' : sick.length ? 'text-warn' : 'text-ok')}>
                  <NumberTicker value={healthy} />
                  <span className="text-fg-dim">/{modules.length}</span>
                </span>
                <span className="micro text-fg-muted">modules healthy</span>
              </>
            ) : (
              <Skeleton className="h-12 w-48" />
            )}
          </p>
          <p className="mt-1 text-[13px] text-fg-dim" aria-live="polite">
            {loading ? 'Checking...' : at ? `Checked ${new Date(at).toLocaleTimeString()}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <Switch id={`${ids}-auto`} checked={auto} onCheckedChange={setAuto} label="Auto-refresh" description="Every 15 seconds" />
          <Button variant="secondary" onClick={() => void refresh()} disabled={loading}>
            {loading ? <Spinner /> : <RefreshCw />} Refresh
          </Button>
        </div>
      </section>

      {healthError && !health ? (
        <ErrorState title="Health check failed" message={healthError.message} code={healthError.code} onRetry={() => void refresh()} art="ai-ally" />
      ) : null}

      {!health && !healthError ? <Skeleton className="h-[420px] w-full" /> : null}

      {health && modules.length === 0 ? <EmptyState icon={CircleDashed} title="No modules reported" /> : null}

      {health && modules.length ? (
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="panel ink-edge relative overflow-hidden p-2 pb-10">
            <MeshDiagram modules={modules} active={focus} onActive={setHover} onPin={(n) => setPinned((p) => (p === n ? null : n))} />
            <Legend />
          </div>
          <ModuleDetail module={shown} outer={focus === OUTER} />
        </div>
      ) : null}

      {health && modules.length ? <ModuleTable modules={modules} onPick={setPinned} /> : null}
    </div>
  )
}

function Legend() {
  return (
    <ul className="absolute bottom-3 left-4 flex flex-wrap gap-3" aria-label="Legend">
      {(['ok', 'degraded', 'failed', 'blocked'] as const).map((s) => (
        <li key={s} className="micro flex items-center gap-1.5 text-fg-dim">
          <span aria-hidden className="size-2 rotate-45" style={{ background: STATE_COLOR[s] }} />
          {STATE_LABEL[s]}
        </li>
      ))}
    </ul>
  )
}

function ModuleDetail({ module, outer }: { module: ModuleRow | null; outer: boolean }) {
  if (outer) {
    return (
      <aside className="panel p-5" aria-live="polite">
        <p className="micro text-violet-hi">Outer layer</p>
        <h3 className="title-display mt-1 text-[30px] text-fg">web</h3>
        <p className="mt-2 text-[14px] text-fg-muted">
          This UI and its local API. Like the cli, it holds no domain logic and reaches every module through the Forge's ports.
        </p>
      </aside>
    )
  }
  if (!module) {
    return (
      <aside className="panel p-5 text-[14px] text-fg-muted">
        Hover or focus a cell to read its purpose and checks. Enter pins it.
      </aside>
    )
  }
  const color = STATE_COLOR[module.state]
  return (
    <aside className="panel flex flex-col gap-3 p-5" aria-live="polite" aria-label={`${module.name} details`}>
      <p className="micro text-[10px] text-fg-dim">Hover or focus a cell; Enter pins it</p>
      <div className="flex items-center justify-between">
        <h3 className="title-display text-[34px] text-fg">{module.name}</h3>
        <Badge style={{ color, borderColor: color }} className="bg-transparent">
          {STATE_LABEL[module.state]}
        </Badge>
      </div>
      <p className="text-[14px] text-fg-muted">{module.purpose}</p>
      {module.detail ? <p className="font-mono text-[12.5px] break-words text-fg-dim">{module.detail}</p> : null}
      <p className="micro text-fg-dim">
        Needs: {module.requires.length ? module.requires.join(', ') : 'no neighbours'}
      </p>
      {module.contract_problems.length ? (
        <ul className="flex flex-col gap-1 text-[13px] text-danger">
          {module.contract_problems.map((p) => (
            <li key={p}>Contract: {p}</li>
          ))}
        </ul>
      ) : null}
      <ul className="flex flex-col gap-1.5 border-t border-line pt-3">
        {module.checks.length === 0 ? <li className="text-[13px] text-fg-dim">No checks ran (the module did not start).</li> : null}
        {module.checks.map((c) => (
          <li key={c.name} className="flex gap-2 text-[13px]">
            {c.ok ? <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-ok" aria-label="passed" /> : <XCircle className="mt-0.5 size-3.5 shrink-0 text-danger" aria-label="failed" />}
            <span className="min-w-0">
              <span className="text-fg">{c.name}</span>
              {c.detail ? <span className="block break-words text-[12px] text-fg-dim">{c.detail}</span> : null}
            </span>
          </li>
        ))}
      </ul>
    </aside>
  )
}

function ModuleTable({ modules, onPick }: { modules: ModuleRow[]; onPick: (name: string) => void }) {
  return (
    <section aria-labelledby="mod-table-h" className="flex flex-col gap-2">
      <SectionLabel>
        <span id="mod-table-h">All modules</span>
      </SectionLabel>
      <div className="overflow-x-auto border border-line">
        <table className="w-full border-collapse text-left text-[13.5px]">
          <thead className="bg-surface-2">
            <tr className="micro text-fg-dim">
              <th scope="col" className="px-3 py-2 font-normal">Module</th>
              <th scope="col" className="px-3 py-2 font-normal">State</th>
              <th scope="col" className="px-3 py-2 font-normal">Detail</th>
              <th scope="col" className="px-3 py-2 font-normal">Needs</th>
              <th scope="col" className="px-3 py-2 text-right font-normal">Checks</th>
            </tr>
          </thead>
          <tbody>
            {modules.map((m) => {
              const passed = m.checks.filter((c) => c.ok).length
              return (
                <tr key={m.name} className="border-t border-line/70 hover:bg-surface-2/60">
                  <th scope="row" className="px-3 py-2 font-normal">
                    <button type="button" onClick={() => onPick(m.name)} className="font-mono text-fg underline-offset-2 hover:text-hazard-hi hover:underline">
                      {m.name}
                    </button>
                  </th>
                  <td className="px-3 py-2">
                    <span className="micro inline-flex items-center gap-1.5" style={{ color: STATE_COLOR[m.state] }}>
                      <Activity className="size-3" aria-hidden />
                      {STATE_LABEL[m.state]}
                    </span>
                    {m.contract_problems.length ? <span className="micro ml-2 text-danger">+{m.contract_problems.length} contract</span> : null}
                  </td>
                  <td className="max-w-[420px] px-3 py-2 text-fg-muted">
                    <span className="line-clamp-2 break-words">{m.detail || m.purpose}</span>
                  </td>
                  <td className="px-3 py-2 font-mono text-[12px] text-fg-dim">{m.requires.join(', ') || '—'}</td>
                  <td className="px-3 py-2 text-right font-mono text-[12px] text-fg-muted">
                    {passed}/{m.checks.length}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
