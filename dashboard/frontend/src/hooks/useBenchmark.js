import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { fetchAPI } from '../api'

const POLL_INTERVAL_MS = 2000
const HISTORY_LIMIT = 50

export default function useBenchmark(serviceName, modelPath) {
  const [params, setParams] = useState({})
  const [paramsLoaded, setParamsLoaded] = useState(false)
  // Fetched from the backend, which owns the set the apply step skips - the
  // badge and the skip-list cannot drift apart.
  const [benchOnlyFlags, setBenchOnlyFlags] = useState(() => new Set())
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState(null)
  const [activeRunId, setActiveRunId] = useState(null)
  const [currentRun, setCurrentRun] = useState(null)
  const [history, setHistory] = useState([])
  const [historyError, setHistoryError] = useState(null)
  const [applyingId, setApplyingId] = useState(null)
  const [applyResult, setApplyResult] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const refreshHistory = useCallback(async () => {
    try {
      const data = await fetchAPI(`/benchmarks?service_name=${encodeURIComponent(serviceName)}&limit=${HISTORY_LIMIT}`)
      if (mountedRef.current) {
        setHistory(data.runs || [])
        setHistoryError(null)
      }
    } catch (e) {
      if (mountedRef.current) setHistoryError(e.message)
    }
  }, [serviceName])

  // Prefill from the service's own params (the endpoint merges its defaults
  // over the bench minimums) and load the history.
  useEffect(() => {
    if (!serviceName) return
    let cancelled = false
    fetchAPI(`/benchmarks/service-defaults/${encodeURIComponent(serviceName)}`)
      .then(data => {
        if (cancelled) return
        setParams(data.params || {})
        setParamsLoaded(true)
      })
      .catch(() => {
        if (!cancelled) {
          setParams({})
          setParamsLoaded(true)
        }
      })
    fetchAPI("/benchmarks/bench-only-flags")
      .then(data => {
        if (!cancelled) setBenchOnlyFlags(new Set(data.flags || []))
      })
      .catch(() => {
        // Cosmetic only: without the list the badges simply don't render,
        // the server's skip-list is what keeps a service safe.
      })
    refreshHistory()
    return () => { cancelled = true }
  }, [serviceName, refreshHistory])

  // Poll the active run until it leaves pending/running. The backend has no
  // stream for bench runs (the executor blocks on the subprocess), so the
  // "live" view is this poll plus the run row's status and elapsed time.
  useEffect(() => {
    if (!activeRunId) return
    let stopped = false
    const poll = async () => {
      try {
        const run = await fetchAPI(`/benchmarks/${activeRunId}`)
        if (stopped) return
        setCurrentRun(run)
        if (run.status !== 'pending' && run.status !== 'running') {
          stopped = true
          setActiveRunId(null)
          refreshHistory()
        }
      } catch {
        // A transient 5xx should not kill the poll; the next tick retries.
      }
    }
    poll()
    const timer = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [activeRunId, refreshHistory])

  const setParam = useCallback((flag, value) => {
    setParams(prev => {
      const next = { ...prev }
      next[flag] = value
      return next
    })
  }, [])

  const removeParam = useCallback((flag) => {
    setParams(prev => {
      const next = { ...prev }
      delete next[flag]
      return next
    })
  }, [])

  const refreshRun = useCallback(async (runId) => {
    try {
      const run = await fetchAPI(`/benchmarks/${runId}`)
      if (!mountedRef.current) return
      setHistory(prev => prev.map(r => (r.id === runId ? { ...r, ...run } : r)))
    } catch {
      // Detail loading is best-effort; the summary row stays as-is.
    }
  }, [])

  const commandPreview = useMemo(() => {
    const parts = [modelPath || '<model>', '-o', 'json']
    for (const [flag, value] of Object.entries(params)) {
      if (!flag) continue
      parts.push(flag)
      if (value) parts.push(value)
    }
    return `llama-bench -m ${parts.join(' ')}`
  }, [params, modelPath])

  const startBenchmark = useCallback(async () => {
    setStarting(true)
    setStartError(null)
    setApplyResult(null)
    const clean = {}
    for (const [flag, value] of Object.entries(params)) {
      if (flag) clean[flag] = value ?? ''
    }
    try {
      const run = await fetchAPI('/benchmarks', {
        method: 'POST',
        body: JSON.stringify({ service_name: serviceName, params: clean }),
      })
      setCurrentRun(run)
      setActiveRunId(run.id)
      return run
    } catch (e) {
      setStartError(e.message)
      // On a 409 the existing run is what the user needs to see; a history
      // refresh surfaces it with its live status.
      refreshHistory()
      throw e
    } finally {
      setStarting(false)
    }
  }, [serviceName, params, refreshHistory])

  const cancelRun = useCallback(async () => {
    if (!activeRunId) return
    try {
      await fetchAPI(`/benchmarks/${activeRunId}`, { method: 'DELETE' })
    } catch {
      // A 404 race (the row was deleted between render and click) lands here;
      // either way the run is no longer live, so the local state drops and
      // the history refresh reconciles.
    } finally {
      setCurrentRun(null)
      setActiveRunId(null)
      await refreshHistory()
    }
  }, [activeRunId, refreshHistory])

  const deleteRun = useCallback(async (runId) => {
    setDeletingId(runId)
    try {
      await fetchAPI(`/benchmarks/${runId}`, { method: 'DELETE' })
      if (activeRunId === runId) {
        setCurrentRun(null)
        setActiveRunId(null)
      }
      await refreshHistory()
    } finally {
      setDeletingId(null)
    }
  }, [activeRunId, refreshHistory])

  const applyRun = useCallback(async (runId) => {
    setApplyingId(runId)
    setApplyResult(null)
    try {
      const result = await fetchAPI(`/benchmarks/${runId}/apply`, { method: 'PUT' })
      setApplyResult(result)
      return result
    } catch (e) {
      setApplyResult({ success: false, message: e.message })
      throw e
    } finally {
      setApplyingId(null)
    }
  }, [])

  const dismissApplyResult = useCallback(() => setApplyResult(null), [])

  const isRunActive = activeRunId !== null

  return {
    params, paramsLoaded, setParam, removeParam, commandPreview, benchOnlyFlags,
    starting, startError, startBenchmark,
    currentRun, isRunActive, cancelRun,
    history, historyError, refreshHistory, refreshRun,
    applyingId, applyResult, applyRun, dismissApplyResult,
    deletingId, deleteRun,
  }
}
