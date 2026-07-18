import { useState, useEffect, useRef } from 'react'
import { fetchAPI } from '../api'
import { getValue } from '../utils'

const POLL_INTERVAL = 200
const MAX_HISTORY = 60

// Map llama.cpp metric names to vLLM-equivalent names so the rest of the hook
// and downstream components can use a single set of keys.
const LLAMACPP_TO_VLLM = {
  'llamacpp:prompt_tokens_total': 'vllm:prompt_tokens_total',
  'llamacpp:tokens_predicted_total': 'vllm:generation_tokens_total',
  'llamacpp:prompt_tokens_seconds': 'vllm:prompt_tokens_seconds',
  'llamacpp:predicted_tokens_seconds': 'vllm:generation_tokens_seconds',
  'llamacpp:requests_processing': 'vllm:num_requests_running',
  'llamacpp:requests_deferred': 'vllm:num_requests_waiting',
}

function normalizeMetrics(raw, engine) {
  if (engine !== 'llamacpp') return raw
  const normalized = {}
  for (const [key, value] of Object.entries(raw)) {
    const mapped = LLAMACPP_TO_VLLM[key] || key
    normalized[mapped] = value
  }
  return normalized
}

export default function useServiceMetrics({ serviceName, enabled }) {
  const [metrics, setMetrics] = useState({})
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [lastScraped, setLastScraped] = useState(null)
  const [engine, setEngine] = useState(null)
  const mountedRef = useRef(true)
  const prevRef = useRef({ timestamp: null, counterPrompt: null, counterGen: null, counterPreempt: null })
  const slotsRef = useRef({})

  useEffect(() => {
    if (!enabled) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMetrics({})
      setHistory([])
      setLoading(false)
      setError(null)
      setLastScraped(null)
      setEngine(null)
      prevRef.current = { timestamp: null, counterPrompt: null, counterGen: null, counterPreempt: null }
      slotsRef.current = {}
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
        const eng = data.engine || 'vllm'
        const normalized = normalizeMetrics(raw, eng)

        let slots = null
        if (eng === 'llamacpp') {
          try {
            const slotsData = await fetchAPI(`/services/${serviceName}/slots`)
            if (pollActive && mountedRef.current) slots = slotsData.slots
          } catch {
            slots = null
          }
        }
        if (!pollActive || !mountedRef.current) return

        setMetrics(normalized)
        setEngine(eng)
        setError(null)
        setLastScraped(data.scraped_at)

        const now = Date.now() / 1000

        const promptTotal = getValue(normalized, 'vllm:prompt_tokens_total')
        const genTotal = getValue(normalized, 'vllm:generation_tokens_total')
        const kvCache = getValue(normalized, 'vllm:kv_cache_usage_perc')
        const prefixHits = getValue(normalized, 'vllm:prefix_cache_hits_total')
        const prefixQueries = getValue(normalized, 'vllm:prefix_cache_queries_total')
        const specAccepted = getValue(normalized, 'vllm:spec_decode_num_accepted_tokens_total')
        const specDraftTokens = getValue(normalized, 'vllm:spec_decode_num_draft_tokens_total')
        const running = getValue(normalized, 'vllm:num_requests_running')
        const waiting = getValue(normalized, 'vllm:num_requests_waiting')
        const preemptTotal = getValue(normalized, 'vllm:num_preemptions_total')

        // llama.cpp's Prometheus throughput gauges are lifetime averages that
        // converge and never decay — useless for a live graph. The /slots
        // endpoint exposes per-slot counters that tick mid-generation:
        // n_decoded (generated tokens) and n_prompt_tokens_processed (prompt
        // progress). Both reset per task, so deltas are tracked per slot and
        // keyed by id_task to avoid negative spikes on task rollover.
        const promptTokensSec = getValue(normalized, 'vllm:prompt_tokens_seconds')
        const genTokensSec = getValue(normalized, 'vllm:generation_tokens_seconds')

        const prev = prevRef.current
        let promptTokensRate = 0
        let generationTokensRate = 0
        let preemptRate = 0

        const dt = prev.timestamp != null ? now - prev.timestamp : 0
        if (eng === 'llamacpp') {
          if (slots != null) {
            let decodedDelta = 0
            let promptDelta = 0
            const seen = {}
            for (const slot of slots) {
              const prevSlot = slotsRef.current[slot.id]
              const nDecoded = slot.n_decoded ?? 0
              const nPrompt = slot.n_prompt_tokens_processed ?? 0
              if (prevSlot && prevSlot.idTask === slot.id_task) {
                if (nDecoded > prevSlot.nDecoded) decodedDelta += nDecoded - prevSlot.nDecoded
                if (nPrompt > prevSlot.nPrompt) promptDelta += nPrompt - prevSlot.nPrompt
              }
              seen[slot.id] = { idTask: slot.id_task, nDecoded, nPrompt }
            }
            slotsRef.current = seen
            if (dt > 0) {
              generationTokensRate = decodedDelta / dt
              promptTokensRate = promptDelta / dt
            }
          } else {
            // /slots unreachable — fall back to the lifetime-average gauges,
            // zeroed while idle
            const busy = (running ?? 0) > 0 ? 1 : 0
            promptTokensRate = promptTokensSec != null ? Math.max(0, promptTokensSec) * busy : 0
            generationTokensRate = genTokensSec != null ? Math.max(0, genTokensSec) * busy : 0
          }
        } else if (dt > 0) {
          if (prev.counterPrompt != null && promptTotal != null) {
            promptTokensRate = Math.max(0, (promptTotal - prev.counterPrompt) / dt)
          }
          if (prev.counterGen != null && genTotal != null) {
            generationTokensRate = Math.max(0, (genTotal - prev.counterGen) / dt)
          }
        }
        if (dt > 0 && prev.counterPreempt != null && preemptTotal != null) {
          preemptRate = Math.max(0, (preemptTotal - prev.counterPreempt) / dt)
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
          kvCache,
          prefixHitRatio,
          specAcceptRatio,
          running,
          waiting,
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

    prevRef.current = { timestamp: null, counterPrompt: null, counterGen: null, counterPreempt: null }
    slotsRef.current = {}
    fetchMetrics()
    const id = setInterval(fetchMetrics, POLL_INTERVAL)

    return () => {
      pollActive = false
      mountedRef.current = false
      clearInterval(id)
    }
  }, [serviceName, enabled])

  return { metrics, history, loading, error, lastScraped, engine }
}
