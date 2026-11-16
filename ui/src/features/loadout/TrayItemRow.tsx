import { ArrowDown, ArrowUp, GripVertical, PencilLine, X } from 'lucide-react'
import { Reorder, useDragControls } from 'motion/react'
import { useId, useState, type CSSProperties } from 'react'
import { CopyButton } from '@/components/fx/copy-button'
import { ElementIcon } from '@/components/item/badges'
import { SerialText } from '@/components/item/serial'
import { elementColor, rarityColor } from '@/components/item/tokens'
import { Input, Textarea } from '@/components/ui/input'
import { elementKey, elementLabel, rarityKey } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { TrayItem } from '@/state/tray'
import { useTray } from '@/state/trayStore'

const iconBtn =
  'grid size-7 place-items-center rounded-[2px] text-fg-dim transition-colors hover:bg-surface-4 hover:text-fg disabled:opacity-30 disabled:hover:bg-transparent'

export function TrayItemRow({
  item,
  groups,
  first,
  last,
}: {
  item: TrayItem
  groups: string[]
  first: boolean
  last: boolean
}) {
  const ids = useId()
  const dispatch = useTray((s) => s.dispatch)
  const controls = useDragControls()
  const [editing, setEditing] = useState(false)
  const rKey = rarityKey(item.rarity)
  const el = elementKey(item.element)
  const shown = item.displayName.trim() || item.name || 'Item'

  return (
    <Reorder.Item
      value={item.id}
      dragListener={false}
      dragControls={controls}
      layout="position"
      className="relative list-none"
      style={{ '--r': rarityColor(rKey) } as CSSProperties}
      whileDrag={{ scale: 1.02, boxShadow: '0 18px 40px -12px rgb(0 0 0 / 0.9)', zIndex: 10 }}
    >
      <div className="relative flex gap-2 border border-line bg-surface-2 py-2 pr-2 pl-1 transition-colors hover:border-line-strong">
        <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-[color:var(--r)]" />
        <button
          type="button"
          aria-label={`Drag to reorder ${shown}`}
          title="Drag to reorder (or use the arrows)"
          onPointerDown={(e) => controls.start(e)}
          className="ml-1 grid w-5 shrink-0 cursor-grab touch-none place-items-center text-fg-dim hover:text-fg active:cursor-grabbing"
          tabIndex={-1}
        >
          <GripVertical className="size-4" />
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <p className="truncate font-display text-[17px] leading-tight font-semibold tracking-wide text-fg uppercase" title={shown}>
              {shown}
            </p>
            {el ? (
              <span style={{ color: elementColor(el) }} title={elementLabel(el)} className="shrink-0">
                <ElementIcon element={el} className="size-3.5" />
                <span className="sr-only">{elementLabel(el)}</span>
              </span>
            ) : null}
          </div>
          <p className="truncate text-[12px] text-fg-dim">
            <span style={{ color: 'var(--r)' }}>{item.rarity ?? 'Unknown'}</span>
            {item.label ? ` / ${item.label}` : ''}
            {item.level !== null ? ` / Lv ${item.level}` : ''}
            {item.displayName.trim() && item.name ? ` / ${item.name}` : ''}
          </p>
          <div className="mt-1 flex items-center gap-1">
            <SerialText serial={item.serial} className="min-w-0 truncate text-[11.5px]" />
          </div>
          {item.note && !editing ? <p className="mt-1 line-clamp-2 text-[12.5px] text-fg-muted italic">{item.note}</p> : null}

          {editing ? (
            <div className="mt-2 flex flex-col gap-2 border-t border-line pt-2">
              <div className="flex flex-col gap-1">
                <label htmlFor={`${ids}-dn`} className="micro text-[10px] text-fg-dim">
                  Display name on the sheet
                </label>
                <Input
                  id={`${ids}-dn`}
                  value={item.displayName}
                  placeholder={item.name}
                  onChange={(e) => dispatch({ type: 'update', id: item.id, patch: { displayName: e.target.value } })}
                  className="h-8 text-[14px]"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor={`${ids}-note`} className="micro text-[10px] text-fg-dim">
                  Note
                </label>
                <Textarea
                  id={`${ids}-note`}
                  value={item.note}
                  rows={2}
                  placeholder="Why it is in the build"
                  onChange={(e) => dispatch({ type: 'update', id: item.id, patch: { note: e.target.value } })}
                  className="min-h-0 text-[13px]"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor={`${ids}-grp`} className="micro text-[10px] text-fg-dim">
                  Group
                </label>
                <select
                  id={`${ids}-grp`}
                  value={item.group}
                  onChange={(e) => dispatch({ type: 'setGroup', id: item.id, group: e.target.value })}
                  className="h-8 rounded-[3px] border border-line-strong bg-bg px-2 text-[13px] text-fg"
                >
                  {groups.map((g) => (
                    <option key={g} value={g}>
                      {g}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          ) : null}
        </div>

        <div className="flex shrink-0 flex-col items-end gap-0.5">
          <div className="flex">
            <button type="button" className={iconBtn} aria-label={`Move ${shown} up`} disabled={first} onClick={() => dispatch({ type: 'move', id: item.id, direction: -1 })}>
              <ArrowUp className="size-3.5" />
            </button>
            <button type="button" className={iconBtn} aria-label={`Move ${shown} down`} disabled={last} onClick={() => dispatch({ type: 'move', id: item.id, direction: 1 })}>
              <ArrowDown className="size-3.5" />
            </button>
            <button type="button" className={cn(iconBtn, 'hover:text-danger')} aria-label={`Remove ${shown}`} onClick={() => dispatch({ type: 'remove', id: item.id })}>
              <X className="size-3.5" />
            </button>
          </div>
          <div className="flex">
            <CopyButton text={item.serial} compact variant="ghost" what={`${shown} code`} className="size-7" />
            <button
              type="button"
              className={cn(iconBtn, editing && 'bg-surface-4 text-hazard-hi')}
              aria-label={`Edit name, note and group of ${shown}`}
              aria-expanded={editing}
              onClick={() => setEditing((v) => !v)}
            >
              <PencilLine className="size-3.5" />
            </button>
          </div>
        </div>
      </div>
    </Reorder.Item>
  )
}
