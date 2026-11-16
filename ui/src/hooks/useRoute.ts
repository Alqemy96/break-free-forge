import { useCallback, useSyncExternalStore } from 'react'
import { buildHash, parseHash, type Route, type Screen } from '@/lib/route'

function subscribe(cb: () => void): () => void {
  window.addEventListener('hashchange', cb)
  return () => window.removeEventListener('hashchange', cb)
}

const getHash = () => window.location.hash

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, getHash, () => '')
  return parseHash(hash)
}

type Params = Record<string, string | number | boolean | null | undefined>

/** Go to a screen. `replace` keeps history clean for state-only updates (filters). */
export function navigate(screen: Screen, params: Params = {}, replace = false): void {
  const next = buildHash(screen, params)
  if (next === window.location.hash) return
  if (replace) {
    window.history.replaceState(null, '', next)
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  } else {
    window.location.hash = next
  }
}

export function useNavigate(): typeof navigate {
  return useCallback(navigate, [])
}
