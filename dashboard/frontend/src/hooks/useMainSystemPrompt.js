import { useState, useEffect, useCallback, useRef } from 'react'
import {
  getMainSystemPrompt,
  putMainSystemPrompt,
  resetMainSystemPrompt,
} from '../services/chatSettings'

// Loads and mutates the global default `main_system_prompt`. `data` is the
// { current, builtin, customized } payload, or null until the first load
// resolves. `save` / `reset` throw on failure so the editor can surface
// the message; on success they refresh `data` from the server response.
export default function useMainSystemPrompt() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const mountedRef = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const d = await getMainSystemPrompt()
      if (!mountedRef.current) return
      setData(d)
      setError(null)
    } catch (e) {
      if (mountedRef.current) setError(e.message || 'Failed to load default prompt')
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
    const d = await putMainSystemPrompt(content)
    if (mountedRef.current) setData(d)
    return d
  }, [])

  const reset = useCallback(async () => {
    const d = await resetMainSystemPrompt()
    if (mountedRef.current) setData(d)
    return d
  }, [])

  return { data, loading, error, refresh, save, reset }
}
