import { useState, useEffect, useCallback, useRef } from 'react'
import { getRegistry, getRegistryJson, putRegistryJson, reloadRegistry } from '../services/mcpRegistry'

export default function useRegistry() {
  const [data, setData] = useState(null)
  const [json, setJson] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const mountedRef = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const [reg, j] = await Promise.all([getRegistry(), getRegistryJson()])
      if (!mountedRef.current) return
      setData(reg)
      setJson(j)
      setError(null)
    } catch (e) {
      if (mountedRef.current) setError(e.message || 'Failed to load registry')
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    refresh()
    return () => { mountedRef.current = false }
  }, [refresh])

  const save = useCallback(async (content) => {
    // Throws on validation failure; caller handles err.body.entry_errors etc.
    const reg = await putRegistryJson(content)
    setData(reg)
    setJson({ content, path: reg.config_file })
    return reg
  }, [])

  const reload = useCallback(async () => {
    const reg = await reloadRegistry()
    const j = await getRegistryJson()
    setData(reg)
    setJson(j)
    return reg
  }, [])

  return { data, json, loading, error, refresh, save, reload }
}
