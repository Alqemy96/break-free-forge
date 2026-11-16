import { AnimatePresence, MotionConfig, motion } from 'motion/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Banners } from '@/components/layout/Banners'
import { Header } from '@/components/layout/Header'
import { NavRail } from '@/components/layout/NavRail'
import { Shortcuts } from '@/components/layout/Shortcuts'
import { Toaster } from '@/components/layout/Toaster'
import { ForgeScreen } from '@/features/forge/ForgeScreen'
import { HealthScreen } from '@/features/health/HealthScreen'
import { BuildSheet } from '@/features/loadout/BuildSheet'
import { TrayDrawer } from '@/features/loadout/TrayDrawer'
import { WorkbenchScreen } from '@/features/workbench/WorkbenchScreen'
import { hasAction, isTypingTarget, overlayOpen, runAction, runEscape } from '@/hooks/useActions'
import { navigate, useRoute } from '@/hooks/useRoute'
import type { Screen } from '@/lib/route'
import { useApp } from '@/state/app'
import { seedTrayLevel } from '@/state/trayStore'

const SCREEN_KEYS: Record<string, Screen> = { '1': 'forge', '2': 'workbench', '3': 'health' }

export function App() {
  const { screen } = useRoute()
  const meta = useApp((s) => s.meta)
  const mainRef = useRef<HTMLElement>(null)
  const [keysOpen, setKeysOpen] = useState(false)

  useEffect(() => {
    void useApp.getState().loadMeta()
    void useApp.getState().refreshHealth()
  }, [])

  useEffect(() => {
    if (meta) seedTrayLevel(meta.level)
  }, [meta])

  // new screen: start at the top and move focus to the content (not on first load)
  const firstScreen = useRef(true)
  useEffect(() => {
    if (firstScreen.current) {
      firstScreen.current = false
      return
    }
    mainRef.current?.scrollTo({ top: 0 })
    mainRef.current?.focus({ preventScroll: true })
  }, [screen])

  const onKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      if (runEscape()) {
        e.preventDefault()
        return
      }
      const active = document.activeElement
      const app = useApp.getState()
      if (active instanceof HTMLElement && active.closest('[data-tray]') && app.trayOpen) {
        app.setTrayOpen(false)
        return
      }
      if (active instanceof HTMLElement && active !== document.body && isTypingTarget(active)) active.blur()
      return
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      const inTray = e.target instanceof Element && e.target.closest('[data-tray]')
      runAction(inTray ? 'build' : 'run')
      return
    }
    if (e.ctrlKey || e.metaKey || e.altKey || isTypingTarget(e.target)) return
    // single-key shortcuts pause while a modal is open (the overlay tray still toggles with L)
    if (overlayOpen() && !(e.key === 'l' || e.key === 'L')) return
    if (e.key === '/') {
      e.preventDefault()
      if (!hasAction('focusSearch')) {
        navigate('forge')
        window.setTimeout(() => runAction('focusSearch'), 380)
      } else {
        runAction('focusSearch')
      }
      return
    }
    if (e.key === 'l' || e.key === 'L') {
      const app = useApp.getState()
      app.setTrayOpen(!app.trayOpen)
      return
    }
    if (e.key === '?') {
      setKeysOpen((v) => !v)
      return
    }
    const target = SCREEN_KEYS[e.key]
    if (target) navigate(target)
  }, [])

  useEffect(() => {
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onKeyDown])

  return (
    <MotionConfig reducedMotion="user">
      <div className="grain flex h-dvh flex-col overflow-hidden">
        <button
          type="button"
          onClick={() => mainRef.current?.focus()}
          className="sr-only z-[70] focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:bg-hazard focus:px-3 focus:py-2 focus:text-hazard-ink"
        >
          Skip to main content
        </button>
        <Header />
        <div className="flex min-h-0 flex-1">
          <NavRail screen={screen} onShortcuts={() => setKeysOpen(true)} />
          <main ref={mainRef} id="main" tabIndex={-1} className="relative min-w-0 flex-1 overflow-y-auto outline-none">
            <Banners screen={screen} />
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={screen}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6, transition: { duration: 0.1 } }}
                transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
              >
                {screen === 'forge' ? <ForgeScreen /> : null}
                {screen === 'workbench' ? <WorkbenchScreen /> : null}
                {screen === 'health' ? <HealthScreen /> : null}
              </motion.div>
            </AnimatePresence>
          </main>
          <TrayDrawer />
        </div>
        <BuildSheet />
        <Shortcuts open={keysOpen} onClose={() => setKeysOpen(false)} />
        <Toaster />
      </div>
    </MotionConfig>
  )
}
