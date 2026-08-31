import { useState, useEffect, useCallback, useRef } from 'react'
import { getOpenRouterCatalog } from '../services/openrouterCatalog'

// Loads the live OpenRouter catalog for the settings picker. `data` is the
// { models, count, fetched_at, stale, cached, configured, known_ids, error }
// payload, or null until the first load resolves.
//
// Loads once on mount and never auto-refreshes: the catalog changes slowly, the
// server caches it, and a silently-changing list under a half-edited selection
// is worse than a stale one. `refresh(true)` is the Refresh button.
export default function useOpenRouterCatalog() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const mountedRef = useRef(true)

  const load = useCallback(async ({ refresh = false } = {}) => {
    try {
      const d = await getOpenRouterCatalog({ refresh })
      if (!mountedRef.current) return
      setData(d)
      setError(null)
    } catch (e) {
      // On a failed refresh a previously-good `data` is kept on purpose: the
      // picker still needs a catalog to render, and `error` carries the retry.
      if (mountedRef.current) setError(e.message || 'Failed to load OpenRouter catalog')
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    load()
    return () => { mountedRef.current = false }
  }, [load])

  return { data, loading, error, refresh: (refresh = true) => load({ refresh }) }
}
