import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MAX_PROVIDER_BATCH, getProviderSummaries } from '../services/openrouterProviders'

// Provider detail for the rows the caller reports as in view.
//
// Fetched per batch and cached per model id, on both sides: passing the same
// ids again costs nothing, and scrolling back to a previously-seen page is
// instant. The map is keyed by model id and rows simply have no provider line
// until their entry lands — a spinner per row would read as broken for the
// ~300 ms a fan-out takes.
//
// `ids` beyond the server's per-batch cap are ignored rather than chunked: the
// point is to cover what the user is looking at, and a list of 425 rows would
// mean 425 upstream requests to describe models nobody is looking at.
//
// An id is asked for once per session. One the server reports in `missing` is
// forgotten, so it comes back with the next batch the pane reports — an id the
// picker stops reporting never comes back on its own, which is what `retry()`
// below is for.
export default function useModelProviders(ids, { limit = MAX_PROVIDER_BATCH } = {}) {
  const [byId, setById] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [retryToken, setRetryToken] = useState(0)
  const requested = useRef(new Set())
  const forceNext = useRef(false)
  const mounted = useRef(true)

  // JSON rather than `join(",")`: a model id is only *usually* comma-free, and a
  // comma inside one would silently split this key into two ids that no such
  // model will ever answer to.
  const key = useMemo(() => JSON.stringify(ids.slice(0, limit)), [ids, limit])

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  useEffect(() => {
    const wanted = JSON.parse(key)
    const force = forceNext.current
    forceNext.current = false
    const missing = wanted.filter((id) => force || !requested.current.has(id))
    if (!missing.length) return
    missing.forEach((id) => requested.current.add(id))
    setLoading(true)
    getProviderSummaries(missing, force ? { force: true } : {})
      .then((data) => {
        if (!mounted.current) return
        setById((prev) => ({ ...prev, ...data.models }))
        setError(null)
        // Ids the server could not fetch must not stay marked as requested,
        // or a transient upstream failure would leave a hole in the map for
        // the rest of the session.
        ;(data.missing || []).forEach((id) => requested.current.delete(id))
      })
      .catch((e) => {
        if (!mounted.current) return
        missing.forEach((id) => requested.current.delete(id))
        setError(e.message || 'Provider detail unavailable')
      })
      .finally(() => { if (mounted.current) setLoading(false) })
  }, [key, retryToken])

  // The one path that forces a refetch. It is what the user clicks precisely
  // when a provider line did not appear, and the server holds a successful
  // lookup for 5 minutes — so without `force` every id it ever managed to fetch
  // would come back unchanged and only the never-cached ones would move. The
  // batch is bounded by what is in view either way, and previously-shown lines
  // are kept until the new ones land.
  const retry = useCallback(() => {
    forceNext.current = true
    requested.current.clear()
    setError(null)
    setRetryToken((t) => t + 1)
  }, [])

  return { byId, loading, error, retry }
}
