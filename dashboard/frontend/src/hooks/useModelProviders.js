import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MAX_PROVIDER_BATCH, getProviderSummaries } from '../services/openrouterProviders'

// Provider detail for the rows currently visible in the catalog pane.
//
// Fetched per batch and cached per model id, on both sides: passing the same
// ids again costs nothing, and scrolling back to a previously-seen page is
// instant. The map is keyed by model id and rows simply have no provider line
// until their entry lands — a spinner per row would read as broken for the
// ~300 ms a fan-out takes.
//
// `ids` beyond the server's per-batch cap are ignored rather than chunked: the
// point is to cover the visible page, and a list of 425 rows would mean 425
// upstream requests to describe models nobody is looking at.
export default function useModelProviders(ids, { limit = MAX_PROVIDER_BATCH } = {}) {
  const [byId, setById] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [retryToken, setRetryToken] = useState(0)
  const requested = useRef(new Set())
  const mounted = useRef(true)

  const key = useMemo(() => ids.slice(0, limit).join(','), [ids, limit])

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  useEffect(() => {
    const wanted = key ? key.split(',') : []
    const missing = wanted.filter((id) => !requested.current.has(id))
    if (!missing.length) return
    missing.forEach((id) => requested.current.add(id))
    setLoading(true)
    getProviderSummaries(missing)
      .then((data) => {
        if (!mounted.current) return
        setById((prev) => ({ ...prev, ...data.models }))
        setError(null)
        // Ids the server could not fetch must not stay marked as requested,
        // or a transient upstream failure would leave a permanent hole in the
        // map for this session.
        ;(data.missing || []).forEach((id) => requested.current.delete(id))
      })
      .catch((e) => {
        if (!mounted.current) return
        missing.forEach((id) => requested.current.delete(id))
        setError(e.message || 'Provider detail unavailable')
      })
      .finally(() => { if (mounted.current) setLoading(false) })
  }, [key, retryToken])

  const retry = useCallback(() => {
    requested.current.clear()
    setById({})
    setRetryToken((t) => t + 1)
  }, [])

  return { byId, loading, error, retry }
}
