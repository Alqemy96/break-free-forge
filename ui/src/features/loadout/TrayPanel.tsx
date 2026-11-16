import { ArrowDown, ArrowUp, Check, FileCode2, FolderPlus, PackageOpen, Pencil, Trash2, X } from 'lucide-react'
import { Reorder } from 'motion/react'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { CopyButton } from '@/components/fx/copy-button'
import { Magnetic } from '@/components/fx/magnetic'
import { ErrorState } from '@/components/item/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field } from '@/components/ui/label'
import { Kbd, Spinner } from '@/components/ui/misc'
import { NumberField } from '@/components/ui/number-field'
import { useAction } from '@/hooks/useActions'
import { plural } from '@/lib/format'
import { itemsInGroup, toBuildRequest, trayCodesText } from '@/state/tray'
import { useTray } from '@/state/trayStore'
import { useBuild } from './buildStore'
import { TrayItemRow } from './TrayItemRow'

export function TrayPanel() {
  const ids = useId()
  const tray = useTray((s) => s.tray)
  const dispatch = useTray((s) => s.dispatch)
  const build = useBuild((s) => s.build)
  const status = useBuild((s) => s.status)
  const source = useBuild((s) => s.source)
  const error = useBuild((s) => s.error)
  const result = useBuild((s) => s.result)
  const openSheet = useBuild((s) => s.openSheet)
  const [newGroup, setNewGroup] = useState('')
  const [confirmClear, setConfirmClear] = useState(false)
  const confirmTimer = useRef<number>(0)
  useEffect(() => () => window.clearTimeout(confirmTimer.current), [])

  const count = tray.items.length
  const building = status === 'loading' && source === 'tray'
  const runBuild = () => {
    if (count === 0 || building) return
    void build(toBuildRequest(tray), 'tray')
  }
  useAction('build', runBuild)

  const clear = () => {
    if (!confirmClear) {
      setConfirmClear(true)
      window.clearTimeout(confirmTimer.current)
      confirmTimer.current = window.setTimeout(() => setConfirmClear(false), 3000)
      return
    }
    setConfirmClear(false)
    dispatch({ type: 'clear' })
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {count === 0 ? (
          <div className="flex flex-col items-center gap-3 border border-dashed border-line-strong px-4 py-10 text-center">
            <PackageOpen className="size-6 text-fg-dim" aria-hidden />
            <p className="title-display text-[20px] text-fg">Tray is empty</p>
            <p className="text-[13.5px] text-fg-muted">
              Add codes from search results or the workbench. They are kept on this computer between visits.
            </p>
          </div>
        ) : null}

        <div className="flex flex-col gap-4">
          {tray.groups.map((group, gi) => (
            <GroupBlock key={group} group={group} index={gi} total={tray.groups.length} />
          ))}
        </div>

        <form
          className="mt-4 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            dispatch({ type: 'addGroup', name: newGroup })
            setNewGroup('')
          }}
        >
          <label htmlFor={`${ids}-ng`} className="sr-only">
            New group name
          </label>
          <Input id={`${ids}-ng`} value={newGroup} onChange={(e) => setNewGroup(e.target.value)} placeholder="New group (e.g. Swap set)" className="h-8 text-[13px]" />
          <Button type="submit" size="sm" variant="secondary" disabled={!newGroup.trim() || tray.groups.includes(newGroup.trim())}>
            <FolderPlus /> Add
          </Button>
        </form>
      </div>

      <div className="flex flex-col gap-3 border-t border-line bg-surface-1 px-4 py-3">
        <div className="grid grid-cols-[1fr_120px] gap-2">
          <Field label="Sheet title" htmlFor={`${ids}-title`}>
            <Input id={`${ids}-title`} value={tray.title} onChange={(e) => dispatch({ type: 'setTitle', title: e.target.value })} className="h-9 text-[14px]" />
          </Field>
          <Field label="Level" htmlFor={`${ids}-lvl`}>
            <NumberField
              id={`${ids}-lvl`}
              value={tray.level}
              min={1}
              max={100}
              placeholder="keep"
              onChange={(level) => dispatch({ type: 'setLevel', level })}
              className="h-9"
              describedBy={`${ids}-lvl-hint`}
            />
          </Field>
        </div>
        <p id={`${ids}-lvl-hint`} className="-mt-1 text-[12px] text-fg-dim">
          {tray.level === null ? 'Level blank: every code keeps its own level.' : `Every code is re-leveled to ${tray.level} on the sheet.`}
        </p>

        {error && source === 'tray' && status === 'error' ? <ErrorState title="Build failed" message={error.message} code={error.code} onRetry={runBuild} /> : null}

        <div className="flex items-center gap-2">
          <Magnetic className="flex-1" strength={0.15}>
            <Button variant="primary" size="lg" className="w-full" onClick={runBuild} disabled={count === 0 || building}>
              {building ? <Spinner /> : <FileCode2 />}
              {building ? 'Building' : `Build sheet${count ? ` (${count})` : ''}`}
            </Button>
          </Magnetic>
          {result && source === 'tray' && status === 'ok' ? (
            <Button variant="secondary" size="lg" className="px-3" onClick={openSheet} aria-label="Open the last built sheet">
              Open
            </Button>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <CopyButton text={trayCodesText(tray)} label="Copy all codes" what="All codes" disabled={count === 0} />
          <p className="micro hidden flex-1 text-center text-[10px] text-fg-dim sm:block">
            <Kbd>Ctrl</Kbd>+<Kbd>Enter</Kbd> in the tray builds
          </p>
          <Button size="sm" variant="danger" onClick={clear} disabled={count === 0} className="ml-auto">
            <Trash2 /> {confirmClear ? 'Confirm clear' : 'Clear'}
          </Button>
        </div>
        <p className="sr-only" aria-live="polite">
          {confirmClear ? 'Press Clear again to remove every item from the tray.' : plural(count, 'item') + ' in the tray'}
        </p>
      </div>
    </div>
  )
}

function GroupBlock({ group, index, total }: { group: string; index: number; total: number }) {
  const ids = useId()
  const tray = useTray((s) => s.tray)
  const dispatch = useTray((s) => s.dispatch)
  const [renaming, setRenaming] = useState(false)
  const [name, setName] = useState(group)
  const items = itemsInGroup(tray, group)

  const commit = () => {
    if (name.trim() && name.trim() !== group) dispatch({ type: 'renameGroup', from: group, to: name })
    setRenaming(false)
  }

  return (
    <section aria-labelledby={`${ids}-h`} className="flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5">
        {renaming ? (
          <form
            className="flex flex-1 gap-1"
            onSubmit={(e) => {
              e.preventDefault()
              commit()
            }}
          >
            <label htmlFor={`${ids}-rn`} className="sr-only">
              Rename group {group}
            </label>
            <Input id={`${ids}-rn`} autoFocus value={name} onChange={(e) => setName(e.target.value)} onBlur={commit} className="h-7 text-[13px]" />
            <button type="submit" className="grid size-7 place-items-center text-ok" aria-label="Save group name">
              <Check className="size-4" />
            </button>
          </form>
        ) : (
          <h3 id={`${ids}-h`} className="micro flex flex-1 items-center gap-2 text-fg-muted">
            <span className="h-px w-3 bg-hazard" aria-hidden />
            {group}
            <span className="text-fg-dim">{items.length}</span>
          </h3>
        )}
        {!renaming ? (
          <div className="flex text-fg-dim">
            <GroupBtn label={`Rename group ${group}`} onClick={() => { setName(group); setRenaming(true) }}>
              <Pencil className="size-3" />
            </GroupBtn>
            <GroupBtn label={`Move group ${group} up`} disabled={index === 0} onClick={() => dispatch({ type: 'moveGroup', name: group, direction: -1 })}>
              <ArrowUp className="size-3" />
            </GroupBtn>
            <GroupBtn label={`Move group ${group} down`} disabled={index === total - 1} onClick={() => dispatch({ type: 'moveGroup', name: group, direction: 1 })}>
              <ArrowDown className="size-3" />
            </GroupBtn>
            <GroupBtn
              label={items.length ? `Group ${group} must be empty to remove it` : `Remove group ${group}`}
              disabled={items.length > 0 || total <= 1}
              onClick={() => dispatch({ type: 'removeGroup', name: group })}
            >
              <X className="size-3" />
            </GroupBtn>
          </div>
        ) : null}
      </div>
      {items.length === 0 ? (
        <p className="border border-dashed border-line px-3 py-2 text-[12.5px] text-fg-dim">Empty. Move items here with their Edit menu.</p>
      ) : (
        <Reorder.Group
          axis="y"
          values={items.map((i) => i.id)}
          onReorder={(order: string[]) => dispatch({ type: 'reorder', group, ids: order })}
          className="flex flex-col gap-1.5"
        >
          {items.map((item, i) => (
            <TrayItemRow key={item.id} item={item} groups={tray.groups} first={i === 0} last={i === items.length - 1} />
          ))}
        </Reorder.Group>
      )}
    </section>
  )
}

function GroupBtn({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="grid size-6 place-items-center rounded-[2px] hover:bg-surface-3 hover:text-fg disabled:opacity-30 disabled:hover:bg-transparent"
    >
      {children}
    </button>
  )
}
