import { useState, useEffect, useRef } from 'react'
import { fetchAPI } from '../api'
import { getValue } from '../utils'

const POLL_INTERVAL = 3000
const MAX_HISTORY = 60

export default function useServiceMetrics({ serviceName, enabled }) {
  const [metrics, setMetrics] = useState({})
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [lastScraped, setLastScraped] = useState(null)
  const mountedRef = useRef(true)
  const prevRef = useRef({ counters: null, timestamp: null })

  useEffect(() => {
    if (!enabled) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMetrics({})
      setHistory([])
      setLoading(false)
      setError(null)
      setLastScraped(null)
      prevRef.current = { counters: null, timestamp: null, counterPrompt: null, counterGen: null, counterPreempt: null }
    }
  }, [enabled])

  useEffect(() => {
    mountedRef.current = true

    if (!enabled) return

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true)
    let pollActive = true

    const fetchMetrics = async () => {
      try {
        const data = await fetchAPI(`/services/${serviceName}/metrics`)
        if (!pollActive || !mountedRef.current) return

        const raw = data.metrics || {}
        setMetrics(raw)
        setError(null)
        setLastScraped(data.scraped_at)

        const now = Date.now() / 1000

        const promptTotal = getValue(raw, 'vllm:prompt_tokens_total')
        const genTotal = getValue(raw, 'vllm:generation_tokens_total')
        const kvCache = getValue(raw, 'vllm:kv_cache_usage_perc')
        const prefixHits = getValue(raw, 'vllm:prefix_cache_hits_total')
        const prefixQueries = getValue(raw, 'vllm:prefix_cache_queries_total')
        const specAccepted = getValue(raw, 'vllm:spec_decode_num_accepted_tokens_total')
        const specDraftTokens = getValue(raw, 'vllm:spec_decode_num_draft_tokens_total')
        const running = getValue(raw, 'vllm:num_requests_running')
        const waiting = getValue(raw, 'vllm:num_requests_waiting')
        const preemptTotal = getValue(raw, 'vllm:num_preemptions_total')

        const prev = prevRef.current
        let promptTokensRate = 0
        let generationTokensRate = 0
        let preemptRate = 0

        const dt = prev.timestamp != null ? now - prev.timestamp : 0
        if (dt > 0) {
          if (prev.counterPrompt != null && promptTotal != null) {
            promptTokensRate = Math.max(0, (promptTotal - prev.counterPrompt) / dt)
          }
          if (prev.counterGen != null && genTotal != null) {
            generationTokensRate = Math.max(0, (genTotal - prev.counterGen) / dt)
          }
          if (prev.counterPreempt != null && preemptTotal != null) {
            preemptRate = Math.max(0, (preemptTotal - prev.counterPreempt) / dt)
          }
        }

        let prefixHitRatio = undefined
        if (prefixQueries !== undefined && prefixQueries > 0) {
          prefixHitRatio = (prefixHits || 0) / prefixQueries
        }

        let specAcceptRatio = undefined
        if (specAccepted != null && specDraftTokens != null && specDraftTokens > 0) {
          specAcceptRatio = specAccepted / specDraftTokens
        }

        const dataPoint = {
          promptTokensRate,
          generationTokensRate,
          kvCache: kvCache !== undefined ? kvCache : undefined,
          prefixHitRatio,
          specAcceptRatio,
          running: running ?? undefined,
          waiting: waiting ?? undefined,
          preemptRate
        }

        setHistory(prevHist => {
          const next = [...prevHist, dataPoint]
          if (next.length > MAX_HISTORY) return next.slice(-MAX_HISTORY)
          return next
        })

        prevRef.current = {
          timestamp: now,
          counterPrompt: promptTotal,
          counterGen: genTotal,
          counterPreempt: preemptTotal
        }

        if (mountedRef.current) setLoading(false)
      } catch (err) {
        if (mountedRef.current) {
          setError(err.message)
          setLoading(false)
        }
      }
    }

    prevRef.current = { counters: null, timestamp: null, counterPrompt: null, counterGen: null, counterPreempt: null }
    fetchMetrics()
    const id = setInterval(fetchMetrics, POLL_INTERVAL)

    return () => {
      pollActive = false
      mountedRef.current = false
      clearInterval(id)
    }
  }, [serviceName, enabled])

  return { metrics, history, loading, error, lastScraped }
}
