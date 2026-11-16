import { Boxes, FileJson, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useId, useRef, useState } from 'react'
import { NumberTicker } from '@/components/fx/number-ticker'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/misc'
import { panelId, tabId, Tabs } from '@/components/ui/tabs'
import { useEscape } from '@/hooks/useActions'
import { useFocusTrap } from '@/hooks/useFocusTrap'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useApp } from '@/state/app'
import { useTray } from '@/state/trayStore'
import { QuickBuild } from './QuickBuild'
import { TrayPanel } from './TrayPanel'

export const TRAY_ID = 'loadout-tray'

/** Docked on wide screens (pushes content), an overlay drawer below 1280px. */
export function TrayDrawer() {
  const base = useId()
  const open = useApp((s) => s.trayOpen)
  const setOpen = useApp((s) => s.setTrayOpen)
  const count = useTray((s) => s.tray.items.length)
  const docked = useMediaQuery('(min-width: 1280px)')
  const [tab, setTab] = useState<'tray' | 'quick'>('tray')
  const panelRef = useRef<HTMLDivElement>(null)

  useEscape(open && !docked, () => setOpen(false))
  useFocusTrap(panelRef, open && !docked)

  useEffect(() => {
    if (open && !docked) panelRef.current?.focus()
  }, [open, docked])

  const body = (
    <div
      ref={panelRef}
      id={TRAY_ID}
      tabIndex={-1}
      data-tray
      role={docked ? 'complementary' : 'dialog'}
      aria-modal={docked ? undefined : true}
      aria-labelledby={`${base}-h`}
      className="flex h-full w-full flex-col outline-none"
    >
      <div aria-hidden className="hazard-stripes h-1 w-full opacity-90" />
      <div className="flex items-center gap-3 px-4 pt-3 pb-2">
        <Boxes className="size-5 text-hazard" aria-hidden />
        <h2 id={`${base}-h`} className="title-display text-[24px] text-fg">
          Loadout
        </h2>
        <span className="rounded-[2px] bg-hazard px-1.5 py-0.5 font-mono text-[12px] font-semibold text-hazard-ink">
          <NumberTicker value={count} />
        </span>
        <span className="micro ml-auto hidden text-[10px] text-fg-dim md:inline">
          <Kbd>L</Kbd> toggle
        </span>
        <Button size="icon-sm" variant="ghost" aria-label="Close the loadout tray" onClick={() => setOpen(false)}>
          <X />
        </Button>
      </div>
      <Tabs
        base={base}
        label="Loadout views"
        value={tab}
        onChange={setTab}
        className="px-2"
        items={[
          { id: 'tray', label: 'Tray', icon: <Boxes aria-hidden /> },
          { id: 'quick', label: 'Quick build', icon: <FileJson aria-hidden /> },
        ]}
      />
      <div role="tabpanel" id={panelId(base, tab)} aria-labelledby={tabId(base, tab)} className="flex min-h-0 flex-1 flex-col">
        {tab === 'tray' ? <TrayPanel /> : <QuickBuild />}
      </div>
    </div>
  )

  if (docked) {
    return (
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="dock"
            className="panel relative h-full shrink-0 overflow-hidden border-y-0 border-r-0"
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 400, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 380, damping: 40 }}
          >
            <div className="h-full w-[400px]">{body}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    )
  }

  return (
    <AnimatePresence>
      {open ? (
        <motion.div key="overlay" className="fixed inset-0 z-40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-black/60" onMouseDown={() => setOpen(false)} aria-hidden />
          <motion.div
            className="panel absolute top-0 right-0 bottom-0 w-[min(420px,100vw)] border-y-0 border-r-0"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 420, damping: 42 }}
          >
            {body}
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}
