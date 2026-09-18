import { useState, useEffect, useCallback, useRef } from 'react'
import { listCaptures, inspectorServices } from '../services/inspector'

export const PAGE_SIZE = 50
export const LIVE_INTERVAL_MS = 5000

// Pure merge for a refresh: new rows arrive at the top (the list is newest
// first), already-shown rows keep their relative order, ids dedupe.
export function mergeReload(existing, fresh) {
  const freshIds = new Set(fresh.map(r => r.id))
  const kept = existing.filter(r => !freshIds.has(r.id))
  return [...fresh, ...kept]
}

// Pure merge for Load more: a later offset page is appended, never reordered,
// and rows that already arrived at the top (a concurrent live tick) dedupe out.
export function appendPage(existing, fresh) {
  const seen = new Set(existing.map(r => r.id))
  return [...existing, ...fresh.filter(r => !seen.has(r.id))]
}

export default function useInspectorCaptures({ service = null, live = false, paused = false } = {}) {
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [services, setServices] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const rowsRef = useRef(rows)
  rowsRef.current = rows

  const fetchPage = useCallback(
    (offset) => listCaptures({ service, limit: PAGE_SIZE, offset }),
    [service]
  )

  // First load, every filter change and every explicit reload: a fresh first
  // page, no merge. Reload exists because merge-based refreshes cannot erase
  // a Load-more'd tail, and Delete-all must empty the list.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      setLoading(true)
      setRows([])
      try {
        const data = await fetchPage(0)
        if (cancelled) return
        setRows(data.captures)
        setTotal(data.total)
      } catch {
        if (cancelled) return
        setRows([])
        setTotal(0)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [fetchPage, reloadToken])

  const reload = useCallback(() => setReloadToken((t) => t + 1), [])

  const refresh = useCallback(async () => {
    setRefreshing(true)
    try {
      const data = await fetchPage(0)
      // Merge rather than replace: a Load-more'd tail must survive a refresh.
      setRows((prev) => (prev.length ? mergeReload(prev, data.captures) : data.captures))
      setTotal(data.total)
    } catch {
      // Keep what is shown; the next tick or manual refresh retries.
    } finally {
      setRefreshing(false)
    }
  }, [fetchPage])

  const loadMore = useCallback(async () => {
    if (rowsRef.current.length >= total) return
    const data = await fetchPage(rowsRef.current.length)
    setRows((prev) => appendPage(prev, data.captures))
    setTotal(data.total)
  }, [fetchPage, total])

  const removeRow = useCallback((id) => {
    setRows((prev) => prev.filter((r) => r.id !== id))
    setTotal((t) => Math.max(0, t - 1))
  }, [])

  const refreshServices = useCallback(async () => {
    try {
      const data = await inspectorServices()
      setServices(data.services || [])
    } catch {
      // The filter list is display-only; an empty list is a valid render.
    }
  }, [])

  useEffect(() => {
    refreshServices()
  }, [refreshServices])

  // Live refetch: the list only — the selected capture and the sub-tab live
  // in the page and are untouched here.
  useEffect(() => {
    if (!live || paused) return undefined
    const id = setInterval(() => {
      fetchPage(0)
        .then((data) => {
          setRows((prev) => (prev.length ? mergeReload(prev, data.captures) : data.captures))
          setTotal(data.total)
        })
        .catch(() => {})
    }, LIVE_INTERVAL_MS)
    return () => clearInterval(id)
  }, [live, paused, fetchPage])

  return {
    rows, total, services, loading, refreshing,
    refresh, reload, loadMore, removeRow, refreshServices,
  }
}
