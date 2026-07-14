import { useState, useEffect, useCallback, useRef } from 'react'
import {
  getOpenRouterModels,
  putOpenRouterModels,
  resetOpenRouterModels,
} from '../services/openrouterModels'

// Loads and mutates the curated OpenRouter model list. `data` is the
// { configured, current, builtin, customized } payload, or null until the
// first load resolves. `save` / `reset` throw on failure so the editor can
// surface the message; on success they refresh `data` from the response.
export default function useOpenRouterModels() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const mountedRef = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const d = await getOpenRouterModels()
      if (!mountedRef.current) return
      setData(d)
      setError(null)
    } catch (e) {
      if (mountedRef.current) setError(e.message || 'Failed to load OpenRouter models')
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    refresh()
    return () => { mountedRef.current = false }
  }, [refresh])

  const save = useCallback(async (models) => {
    const d = await putOpenRouterModels(models)
    if (mountedRef.current) setData(d)
    return d
  }, [])

  const reset = useCallback(async () => {
    const d = await resetOpenRouterModels()
    if (mountedRef.current) setData(d)
    return d
  }, [])

  return { data, loading, error, refresh, save, reset }
}
