import { useCallback, useEffect, useRef, useState } from 'react'
import { deleteProvider, getProviderSettings, putProvider, testProvider } from '../services/providers'

export default function useProviderSettings() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const mounted = useRef(true)

  const refresh = useCallback(() => getProviderSettings().then(
    (d) => {
      if (!mounted.current) return
      setData(d)
      setError(null)
    },
    (e) => {
      if (mounted.current) setError(e.message || 'Failed to load providers')
    },
  ), [])

  useEffect(() => {
    mounted.current = true
    refresh()
    return () => { mounted.current = false }
  }, [refresh])

  const save = useCallback(async (id, body) => {
    const d = await putProvider(id, body)
    if (mounted.current) setData(d)
    return d
  }, [])

  const remove = useCallback(async (id) => {
    const d = await deleteProvider(id)
    if (mounted.current) setData(d)
    return d
  }, [])

  return { data, error, refresh, save, remove, test: testProvider }
}
