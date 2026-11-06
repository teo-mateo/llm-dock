import { useCallback, useEffect, useRef, useState } from 'react'
import { getProviderModels } from '../services/providers'

// Configured providers with the chat models they serve, for the model pickers.
// A provider without a key, or whose catalog failed, contributes no models.
export default function useProviderModels() {
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)
  const mounted = useRef(true)

  const refresh = useCallback(async (opts) => {
    try {
      const d = await getProviderModels(opts)
      if (mounted.current) setProviders(d.providers || [])
    } catch {
      if (mounted.current) setProviders([])
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    refresh()
    return () => { mounted.current = false }
  }, [refresh])

  const groups = providers.filter(p => p.configured && p.models.length > 0)
  return { providers, groups, loading, refresh }
}
