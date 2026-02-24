import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { fetchAPI } from '../api'

export const BENCHMARK_ONLY_FLAGS = new Set(['-m', '-p', '-n', '-r', '-o', '-pg', '-d', '-oe', '-v', '--delay', '--list-devices'])
export const AUTO_ADDED_FLAGS = new Set(['-m', '-o'])
export const SAFE_DEFAULTS = { '-p': '512', '-n': '128', '-r': '3' }
export const APPLY_DENYLIST = ['-p', '-n', '-r', '-o', '-m']
const POLL_INTERVAL = 2000

let nextId = 1

function makeParamRows(paramsObj) {
  const entries = Object.entries(paramsObj)
  const bench = entries.filter(([flag]) => BENCHMARK_ONLY_FLAGS.has(flag))
  const rest = entries.filter(([flag]) => !BENCHMARK_ONLY_FLAGS.has(flag))
  const rows = bench.concat(rest).map(([flag, value]) => ({
    id: nextId++,
    flag,
    value,
    isEmpty: false,
  }))
  rows.push({ id: nextId++, flag: '', value: '', isEmpty: true })
  return rows
}

export default function useBenchmark(serviceName, modelPath) {
  const [params, setParams] = useState(() => makeParamRows(SAFE_DEFAULTS))
  const [isRunning, setIsRunning] = useState(false)
  const [currentRunId, setCurrentRunId] = useState(null)
  const [runStatus, setRunStatus] = useState('idle')
  const [liveOutput, setLiveOutput] = useState('Waiting for benchmark run...')
  const [liveOutputClass, setLiveOutputClass] = useState('text-gray-400')
  const [history, setHistory] = useState([])
  const [paramReference, setParamReference] = useState([])
  const pollRef = useRef(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const refreshHistory = useCallback(async () => {
    try {
      const data = await fetchAPI(`/benchmarks?service_name=${encodeURIComponent(serviceName)}&limit=50`)
      if (mountedRef.current) {
        setHistory((data.runs || []).map(r => ({
          id: r.id,
          date: r.created_at ? r.created_at.replace('T', ' ').substring(0, 19) : '',
          pp_ts: r.pp_avg_ts,
          tg_ts: r.tg_avg_ts,
          params: r.params || {},
          status: r.status,
        })))
      }
    } catch (e) {
      console.error('Failed to refresh history:', e)
    }
  }, [serviceName])

  // Init: load recent params, history, and param reference
  useEffect(() => {
    if (!serviceName) return

    async function init() {
      try {
        const histData = await fetchAPI(`/benchmarks?service_name=${encodeURIComponent(serviceName)}&limit=1`)
        if (histData.runs && histData.runs.length > 0) {
          if (mountedRef.current) setParams(makeParamRows(histData.runs[0].params || {}))
        }
      } catch {
        // fall back to SAFE_DEFAULTS (already set)
      }

      await refreshHistory()

      try {
        const data = await fetchAPI('/flag-metadata/llamacpp_bench')
        const flags = data.optional_flags || {}
        const ref = Object.values(flags).map(f => {
          const isLong = f.cli.startsWith('--')
          return {
            cat: f.category || 'Other',
            flag: isLong ? '' : f.cli,
            long: isLong ? f.cli : '',
            desc: f.description || '',
            def: f.default || '',
            tip: f.tip || '',
          }
        })
        if (mountedRef.current) setParamReference(ref)
      } catch {
        if (mountedRef.current) setParamReference([])
      }
    }

    init()
  }, [serviceName, refreshHistory])

  // Command preview
  const commandPreview = useMemo(() => {
    const nonEmpty = params.filter(p => !p.isEmpty && p.flag)
    let cmd = `llama-bench -m ${modelPath || '<model>'} -o json`
    nonEmpty.forEach(p => {
      cmd += ` ${p.flag}`
      if (p.value) cmd += ` ${p.value}`
    })
    return cmd
  }, [params, modelPath])

  // Param management helpers
  const ensureEmptyRow = useCallback((rows) => {
    if (rows.some(r => r.isEmpty)) return rows
    return [...rows, { id: nextId++, flag: '', value: '', isEmpty: true }]
  }, [])

  const setParamFlag = useCallback((id, flag) => {
    setParams(prev => {
      const updated = prev.map(p => {
        if (p.id !== id) return p
        if (p.isEmpty) return { ...p, flag, isEmpty: false }
        return { ...p, flag }
      })
      return ensureEmptyRow(updated)
    })
  }, [ensureEmptyRow])

  const setParamValue = useCallback((id, value) => {
    setParams(prev => {
      const updated = prev.map(p => {
        if (p.id !== id) return p
        if (p.isEmpty) return { ...p, value, isEmpty: false }
        return { ...p, value }
      })
      return ensureEmptyRow(updated)
    })
  }, [ensureEmptyRow])

  const removeParam = useCallback((id) => {
    setParams(prev => {
      const row = prev.find(p => p.id === id)
      if (!row || row.isEmpty) return prev
      return ensureEmptyRow(prev.filter(p => p.id !== id))
    })
  }, [ensureEmptyRow])

  const addParam = useCallback((flag, value) => {
    let added = false
    setParams(prev => {
      if (prev.some(p => !p.isEmpty && p.flag === flag)) return prev
      added = true
      const newRow = { id: nextId++, flag, value, isEmpty: false }
      const emptyIdx = prev.findIndex(p => p.isEmpty)
      if (emptyIdx >= 0) {
        const updated = [...prev]
        updated.splice(emptyIdx, 0, newRow)
        return updated
      }
      return ensureEmptyRow([...prev, newRow])
    })
    return added
  }, [ensureEmptyRow])

  const resetToDefaults = useCallback(() => {
    setParams(makeParamRows(SAFE_DEFAULTS))
  }, [])

  const loadParams = useCallback((paramsObj) => {
    setParams(makeParamRows(paramsObj))
  }, [])

  // Polling
  useEffect(() => {
    if (!currentRunId) return

    const poll = async () => {
      try {
        const run = await fetchAPI(`/benchmarks/${currentRunId}`)

        if (run.status === 'running') {
          setRunStatus('running')
        } else if (run.status === 'completed') {
          if (pollRef.current) clearInterval(pollRef.current)
          pollRef.current = null
          setIsRunning(false)
          setCurrentRunId(null)
          setRunStatus('completed')

          let resultText = 'Benchmark completed.\n'
          if (run.pp_avg_ts != null) resultText += `\nPrompt Processing: ${run.pp_avg_ts.toFixed(2)} t/s`
          if (run.pp_stddev_ts != null) resultText += ` (stddev: ${run.pp_stddev_ts.toFixed(2)})`
          if (run.tg_avg_ts != null) resultText += `\nText Generation:   ${run.tg_avg_ts.toFixed(2)} t/s`
          if (run.tg_stddev_ts != null) resultText += ` (stddev: ${run.tg_stddev_ts.toFixed(2)})`
          if (run.build_commit) resultText += `\n\nbuild: ${run.build_commit}`
          if (run.gpu_info) resultText += `\ngpu:   ${run.gpu_info}`
          if (run.raw_output) resultText += `\n\n--- Raw Output ---\n${run.raw_output}`

          setLiveOutput(resultText)
          setLiveOutputClass('text-green-400')
          await refreshHistory()
        } else if (run.status === 'failed' || run.status === 'cancelled') {
          if (pollRef.current) clearInterval(pollRef.current)
          pollRef.current = null
          setIsRunning(false)
          setCurrentRunId(null)
          setRunStatus(run.status)

          setLiveOutput(`Benchmark ${run.status}.\n\n${run.error_message || ''}`)
          setLiveOutputClass('text-red-400')
          await refreshHistory()
        }
      } catch (e) {
        console.error('Poll error:', e)
      }
    }

    pollRef.current = setInterval(poll, POLL_INTERVAL)
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [currentRunId, refreshHistory])

  // Run benchmark
  const runBenchmark = useCallback(async () => {
    if (isRunning) return { success: false, error: 'Already running' }

    const paramsObj = {}
    params.forEach(p => {
      if (!p.isEmpty && p.flag) paramsObj[p.flag] = p.value
    })

    setIsRunning(true)
    setRunStatus('running')
    setLiveOutputClass('text-green-400')

    try {
      const data = await fetchAPI('/benchmarks', {
        method: 'POST',
        body: JSON.stringify({ service_name: serviceName, params: paramsObj }),
      })

      setCurrentRunId(data.id)
      setLiveOutput(`Benchmark started (${data.id}).\nWaiting for results...\n`)
      return { success: true }
    } catch (e) {
      setIsRunning(false)
      setRunStatus('idle')
      return { success: false, error: e.message }
    }
  }, [isRunning, params, serviceName])

  // History actions
  const rerunFromHistory = useCallback((runId) => {
    const row = history.find(r => r.id === runId)
    if (!row) return
    loadParams(row.params)
  }, [history, loadParams])

  const getApplyPreview = useCallback((runId) => {
    const row = history.find(r => r.id === runId)
    if (!row) return null

    const applicable = {}
    const skipped = []
    Object.entries(row.params).forEach(([flag, value]) => {
      if (APPLY_DENYLIST.includes(flag)) skipped.push(flag)
      else applicable[flag] = value
    })

    const appliedStr = Object.entries(applicable)
      .map(([k, v]) => v ? `${k} ${v}` : k)
      .join(', ')

    return { applicable, skipped, appliedStr }
  }, [history])

  const applyToService = useCallback(async (runId) => {
    try {
      const data = await fetchAPI(`/benchmarks/${runId}/apply`, { method: 'PUT' })
      return { success: true, message: data.message || 'Configuration applied' }
    } catch (e) {
      return { success: false, error: e.message }
    }
  }, [])

  const deleteRun = useCallback(async (runId) => {
    try {
      await fetchAPI(`/benchmarks/${runId}`, { method: 'DELETE' })
      await refreshHistory()
      return { success: true }
    } catch (e) {
      return { success: false, error: e.message }
    }
  }, [refreshHistory])

  return {
    params,
    isRunning,
    runStatus,
    liveOutput,
    liveOutputClass,
    history,
    paramReference,
    commandPreview,
    setParamFlag,
    setParamValue,
    removeParam,
    addParam,
    resetToDefaults,
    loadParams,
    runBenchmark,
    rerunFromHistory,
    getApplyPreview,
    applyToService,
    deleteRun,
  }
}
