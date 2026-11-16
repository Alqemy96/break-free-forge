import { useEffect, useRef, useState } from 'react'
import { api } from '@/api'
import { useAction } from '@/hooks/useActions'
import { navigate, useRoute } from '@/hooks/useRoute'
import { useApp } from '@/state/app'
import { formFromHash, formToHash, hashHasSearch } from './form'
import { Results } from './Results'
import { SearchPanel } from './SearchPanel'
import { useForge } from './store'

let manufacturerCache: string[] | null = null

export function ForgeScreen() {
  const route = useRoute()
  const meta = useApp((s) => s.meta)
  const queryRef = useRef<HTMLInputElement>(null)
  const [manufacturers, setManufacturers] = useState<string[]>(manufacturerCache ?? [])

  const run = () => {
    const form = useForge.getState().form
    navigate('forge', formToHash(form), true)
    void useForge.getState().run()
  }

  useAction('run', run)
  useAction('focusSearch', () => {
    queryRef.current?.focus()
    queryRef.current?.select()
  })

  // arrive with a search in the hash (reload, back/forward, shared link): restore and run it
  const arrived = useRef(false)
  useEffect(() => {
    if (arrived.current || !meta) return
    arrived.current = true
    const st = useForge.getState()
    if (hashHasSearch(route.params)) {
      const form = formFromHash(route.params, meta.level)
      const same = st.ran && JSON.stringify(formToHash(st.ran)) === JSON.stringify(formToHash(form))
      st.replaceForm(form)
      if (!same) void st.run()
    } else if (st.ran === null && st.form.level === null) {
      st.setForm({ level: meta.level })
    }
  }, [meta, route.params])

  useEffect(() => {
    if (manufacturerCache) return
    const ctrl = new AbortController()
    api
      .stats({ signal: ctrl.signal })
      .then((stats) => {
        manufacturerCache = Object.keys(stats.by_manufacturer ?? {}).sort((a, b) => a.localeCompare(b))
        setManufacturers(manufacturerCache)
      })
      .catch(() => undefined)
    return () => ctrl.abort()
  }, [])

  return (
    <div className="grid min-h-full gap-5 p-4 md:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[minmax(300px,340px)_minmax(0,1fr)] xl:gap-6 xl:p-6">
      <h1 className="sr-only">Forge: search the serial catalog</h1>
      <aside className="panel h-max p-4 md:sticky md:top-4 md:max-h-[calc(100dvh-56px-2rem)] md:overflow-y-auto xl:top-0 xl:max-h-[calc(100dvh-56px-3rem)]">
        <SearchPanel queryRef={queryRef} manufacturers={manufacturers} onRun={run} />
      </aside>
      <Results onRun={run} />
    </div>
  )
}
