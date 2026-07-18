import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import useServiceMetrics from './useServiceMetrics'

const mockMetrics = {
  'vllm:prompt_tokens_total': { '{}': 50000 },
  'vllm:generation_tokens_total': { '{}': 120000 },
  'vllm:kv_cache_usage_perc': { 'gpu_id=0': 0.72 },
  'vllm:prefix_cache_queries_total': { '{}': 1000 },
  'vllm:prefix_cache_hits_total': { '{}': 800 },
  'vllm:spec_decode_num_accepted_tokens_per_pos_total': {
    'position_0': 1000,
    'position_1': 500,
    'position_2': 0
  },
  'vllm:spec_decode_num_accepted_tokens_total': { '{}': 1500 },
  'vllm:spec_decode_num_draft_tokens_total': { '{}': 3000 },
  'vllm:num_requests_running': { '{}': 3 },
  'vllm:num_requests_waiting': { '{}': 1 },
  'vllm:num_preemptions_total': { '{}': 0 }
}

const mockFetchAPI = vi.fn()
vi.mock('../api', () => ({
  fetchAPI: (...args) => mockFetchAPI(...args)
}))

beforeEach(() => {
  vi.useFakeTimers()
  mockFetchAPI.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useServiceMetrics', () => {
  it('returns empty state when disabled', () => {
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'test', enabled: false }))
    expect(result.current.metrics).toEqual({})
    expect(result.current.history).toEqual([])
    expect(result.current.loading).toBe(false)
  })

  it('sets loading true on initial fetch when enabled', async () => {
    mockFetchAPI.mockResolvedValueOnce({ metrics: mockMetrics, scraped_at: '2026-01-01T00:00:00Z' })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'test', enabled: true }))
    expect(result.current.loading).toBe(true)
    await act(async () => {
      vi.advanceTimersByTime(0)
    })
    expect(result.current.loading).toBe(false)
  })

  it('populates metrics and history on successful fetch', async () => {
    mockFetchAPI.mockResolvedValue({ metrics: mockMetrics, scraped_at: '2026-01-01T00:00:00Z' })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.metrics).toEqual(mockMetrics)
    expect(result.current.history.length).toBe(1)
    expect(result.current.lastScraped).toBe('2026-01-01T00:00:00Z')
  })

  it('first scrape yields zero rates', async () => {
    mockFetchAPI.mockResolvedValue({ metrics: mockMetrics, scraped_at: '2026-01-01T00:00:00Z' })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    const firstPoint = result.current.history[0]
    expect(firstPoint.promptTokensRate).toBe(0)
    expect(firstPoint.generationTokensRate).toBe(0)
    expect(firstPoint.preemptRate).toBe(0)
  })

  it('derives correct token rates from counter deltas', async () => {
    mockFetchAPI.mockResolvedValueOnce({
      metrics: {
        'vllm:prompt_tokens_total': { '{}': 1000 },
        'vllm:generation_tokens_total': { '{}': 2000 },
        'vllm:num_preemptions_total': { '{}': 0 },
        'vllm:kv_cache_usage_perc': { 'gpu_id=0': 0.5 },
        'vllm:num_requests_running': { '{}': 1 },
        'vllm:num_requests_waiting': { '{}': 0 },
        'vllm:prefix_cache_queries_total': { '{}': 10 },
        'vllm:prefix_cache_hits_total': { '{}': 5 }
      },
      scraped_at: new Date().toISOString()
    })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    mockFetchAPI.mockResolvedValueOnce({
      metrics: {
        'vllm:prompt_tokens_total': { '{}': 2000 },
        'vllm:generation_tokens_total': { '{}': 4000 },
        'vllm:num_preemptions_total': { '{}': 2 },
        'vllm:kv_cache_usage_perc': { 'gpu_id=0': 0.6 },
        'vllm:num_requests_running': { '{}': 2 },
        'vllm:num_requests_waiting': { '{}': 1 },
        'vllm:prefix_cache_queries_total': { '{}': 20 },
        'vllm:prefix_cache_hits_total': { '{}': 15 }
      },
      scraped_at: new Date().toISOString()
    })
    await act(async () => {
      vi.advanceTimersByTime(3000)
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.history.length).toBe(2)
    const secondPoint = result.current.history[1]
    expect(secondPoint.promptTokensRate).toBeGreaterThan(0)
    expect(secondPoint.generationTokensRate).toBeGreaterThan(0)
    expect(secondPoint.preemptRate).toBeGreaterThan(0)
  })

  it('correctly computes prefix hit ratio', async () => {
    mockFetchAPI.mockResolvedValue({ metrics: mockMetrics, scraped_at: '2026-01-01T00:00:00Z' })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.history[0].prefixHitRatio).toBeCloseTo(0.8)
  })

  it('correctly computes spec decode accept ratio', async () => {
    mockFetchAPI.mockResolvedValue({ metrics: mockMetrics, scraped_at: '2026-01-01T00:00:00Z' })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.history[0].specAcceptRatio).toBeCloseTo(0.5)
  })

  it('bounded history shifts oldest entries beyond 60', async () => {
    mockFetchAPI.mockResolvedValue({ metrics: mockMetrics, scraped_at: '2026-01-01T00:00:00Z' })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    for (let i = 0; i < 65; i++) {
      await act(async () => {
        vi.advanceTimersByTime(3000)
        await Promise.resolve()
        await Promise.resolve()
      })
    }
    expect(result.current.history.length).toBe(60)
  })

  it('sets error on failed fetch', async () => {
    mockFetchAPI.mockRejectedValue(new Error('Connection refused'))
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.error).toBe('Connection refused')
  })

  it('preserves history on error after successful scrapes', async () => {
    mockFetchAPI.mockResolvedValueOnce({ metrics: mockMetrics, scraped_at: '2026-01-01T00:00:00Z' })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.history.length).toBe(1)
    expect(result.current.error).toBeNull()

    mockFetchAPI.mockRejectedValueOnce(new Error('Connection refused'))
    mockFetchAPI.mockResolvedValueOnce({ metrics: mockMetrics, scraped_at: '2026-01-01T00:00:02Z' })
    await act(async () => {
      vi.advanceTimersByTime(200)
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.history.length).toBe(1)
    expect(result.current.error).toBe('Connection refused')
  })

  it('resets state when enabled changes to false', async () => {
    mockFetchAPI.mockResolvedValue({ metrics: mockMetrics, scraped_at: '2026-01-01T00:00:00Z' })
    const { result, rerender } = renderHook(
      ({ serviceName, enabled }) => useServiceMetrics({ serviceName, enabled }),
      { initialProps: { serviceName: 'test', enabled: true } }
    )
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.history.length).toBe(1)
    rerender({ serviceName: 'test', enabled: false })
    expect(result.current.metrics).toEqual({})
    expect(result.current.history).toEqual([])
    expect(result.current.loading).toBe(false)
  })

  it('normalizes llama.cpp metric names to vLLM equivalents', async () => {
    const llamacppMetrics = {
      'llamacpp:prompt_tokens_total': { '{}': 25000 },
      'llamacpp:tokens_predicted_total': { '{}': 60000 },
      'llamacpp:prompt_tokens_seconds': { '{}': 500 },
      'llamacpp:predicted_tokens_seconds': { '{}': 100 },
      'llamacpp:requests_processing': { '{}': 2 },
      'llamacpp:requests_deferred': { '{}': 1 },
    }
    mockFetchAPI.mockResolvedValue({ metrics: llamacppMetrics, engine: 'llamacpp', scraped_at: '2026-01-01T00:00:00Z' })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'llamacpp-test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.engine).toBe('llamacpp')
    expect(result.current.metrics).toHaveProperty('vllm:prompt_tokens_total')
    expect(result.current.metrics).toHaveProperty('vllm:generation_tokens_total')
    expect(result.current.metrics).toHaveProperty('vllm:prompt_tokens_seconds')
    expect(result.current.metrics).toHaveProperty('vllm:generation_tokens_seconds')
    expect(result.current.metrics).toHaveProperty('vllm:num_requests_running')
    expect(result.current.metrics).toHaveProperty('vllm:num_requests_waiting')
    expect(result.current.metrics).not.toHaveProperty('llamacpp:prompt_tokens_total')
    expect(result.current.metrics).not.toHaveProperty('llamacpp:tokens_predicted_total')
  })

  it('leaves vLLM metric names unchanged', async () => {
    mockFetchAPI.mockResolvedValue({ metrics: mockMetrics, engine: 'vllm', scraped_at: '2026-01-01T00:00:00Z' })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'vllm-test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.engine).toBe('vllm')
    expect(result.current.metrics).toHaveProperty('vllm:prompt_tokens_total')
    expect(result.current.metrics).toHaveProperty('vllm:generation_tokens_total')
  })

const llamacppMetricsBase = {
  metrics: {
    'llamacpp:prompt_tokens_total': { '{}': 1000 },
    'llamacpp:tokens_predicted_total': { '{}': 2000 },
    'llamacpp:prompt_tokens_seconds': { '{}': 500 },
    'llamacpp:predicted_tokens_seconds': { '{}': 60 },
    'llamacpp:requests_processing': { '{}': 1 },
    'llamacpp:requests_deferred': { '{}': 0 },
  },
  engine: 'llamacpp',
  scraped_at: '2026-01-01T00:00:00Z'
}

function slotsPayload(slots) {
  return { slots, scraped_at: '2026-01-01T00:00:00Z' }
}

function queueLlamaCpp({ metrics, slots }) {
  const metricsQueue = (Array.isArray(metrics) ? metrics : [metrics]).slice()
  const slotsQueue = (Array.isArray(slots) ? slots : [slots]).slice()
  mockFetchAPI.mockImplementation((path) => {
    if (path.includes('/slots')) {
      const next = slotsQueue.length > 1 ? slotsQueue.shift() : slotsQueue[0]
      return next instanceof Error ? Promise.reject(next) : Promise.resolve(next)
    }
    const next = metricsQueue.length > 1 ? metricsQueue.shift() : metricsQueue[0]
    return next instanceof Error ? Promise.reject(next) : Promise.resolve(next)
  })
}

describe('useServiceMetrics llama.cpp slots', () => {
  it('derives live generation rate from slot n_decoded deltas', async () => {
    queueLlamaCpp({
      metrics: llamacppMetricsBase,
      slots: [
        slotsPayload([{ id: 0, is_processing: true, id_task: 100, n_decoded: 1000, n_prompt_tokens: 500, n_prompt_tokens_processed: 500 }]),
        slotsPayload([{ id: 0, is_processing: true, id_task: 100, n_decoded: 1200, n_prompt_tokens: 500, n_prompt_tokens_processed: 500 }]),
      ]
    })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'llamacpp-test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    await act(async () => {
      vi.advanceTimersByTime(3000)
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.history.length).toBeGreaterThanOrEqual(3)
    // first scrape establishes the baseline — no delta yet
    expect(result.current.history[0].generationTokensRate).toBe(0)
    // second scrape sees n_decoded 1000 -> 1200
    expect(result.current.history[1].generationTokensRate).toBeGreaterThan(0)
    // subsequent scrapes see no further movement
    expect(result.current.history[2].generationTokensRate).toBe(0)
  })

  it('derives prompt rate from slot n_prompt_tokens_processed deltas', async () => {
    queueLlamaCpp({
      metrics: llamacppMetricsBase,
      slots: [
        slotsPayload([{ id: 0, is_processing: true, id_task: 100, n_decoded: 0, n_prompt_tokens: 800, n_prompt_tokens_processed: 500 }]),
        slotsPayload([{ id: 0, is_processing: true, id_task: 100, n_decoded: 0, n_prompt_tokens: 800, n_prompt_tokens_processed: 800 }]),
      ]
    })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'llamacpp-test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    await act(async () => {
      vi.advanceTimersByTime(3000)
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.history[0].promptTokensRate).toBe(0)
    expect(result.current.history[1].promptTokensRate).toBeGreaterThan(0)
    expect(result.current.history[1].generationTokensRate).toBe(0)
  })

  it('task rollover resets the baseline without a negative spike', async () => {
    queueLlamaCpp({
      metrics: llamacppMetricsBase,
      slots: [
        slotsPayload([{ id: 0, is_processing: true, id_task: 100, n_decoded: 1500, n_prompt_tokens: 500, n_prompt_tokens_processed: 500 }]),
        slotsPayload([{ id: 0, is_processing: true, id_task: 101, n_decoded: 5, n_prompt_tokens: 300, n_prompt_tokens_processed: 300 }]),
        slotsPayload([{ id: 0, is_processing: true, id_task: 101, n_decoded: 25, n_prompt_tokens: 300, n_prompt_tokens_processed: 300 }]),
      ]
    })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'llamacpp-test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    await act(async () => {
      vi.advanceTimersByTime(200)
      await Promise.resolve()
      await Promise.resolve()
    })
    // task changed 100 -> 101 with n_decoded reset to 5: delta discarded, rate 0
    expect(result.current.history[1].generationTokensRate).toBe(0)
    await act(async () => {
      vi.advanceTimersByTime(200)
      await Promise.resolve()
      await Promise.resolve()
    })
    // same task 101, n_decoded 5 -> 25: real delta
    expect(result.current.history[2].generationTokensRate).toBeGreaterThan(0)
  })

  it('idle slots yield zero rates even with stale throughput gauges', async () => {
    queueLlamaCpp({
      metrics: {
        metrics: {
          'llamacpp:prompt_tokens_total': { '{}': 1000 },
          'llamacpp:tokens_predicted_total': { '{}': 2000 },
          'llamacpp:prompt_tokens_seconds': { '{}': 1954 },
          'llamacpp:predicted_tokens_seconds': { '{}': 104 },
          'llamacpp:requests_processing': { '{}': 0 },
          'llamacpp:requests_deferred': { '{}': 0 },
        },
        engine: 'llamacpp',
        scraped_at: '2026-01-01T00:00:00Z'
      },
      slots: slotsPayload([
        { id: 0, is_processing: false, id_task: 100, n_decoded: 1602, n_prompt_tokens: 4834, n_prompt_tokens_processed: 2129 },
      ])
    })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'llamacpp-test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    await act(async () => {
      vi.advanceTimersByTime(3000)
      await Promise.resolve()
      await Promise.resolve()
    })
    for (const point of result.current.history) {
      expect(point.promptTokensRate).toBe(0)
      expect(point.generationTokensRate).toBe(0)
    }
    expect(result.current.history[0].running).toBe(0)
  })

  it('falls back to throughput gauges when the slots endpoint fails', async () => {
    queueLlamaCpp({
      metrics: llamacppMetricsBase,
      slots: new Error('404')
    })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'llamacpp-test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.history.length).toBeGreaterThanOrEqual(1)
    const firstPoint = result.current.history[0]
    expect(firstPoint.promptTokensRate).toBe(500)
    expect(firstPoint.generationTokensRate).toBe(60)
  })

  it('gauge fallback is zeroed while idle', async () => {
    queueLlamaCpp({
      metrics: {
        metrics: {
          'llamacpp:prompt_tokens_total': { '{}': 1000 },
          'llamacpp:tokens_predicted_total': { '{}': 2000 },
          'llamacpp:prompt_tokens_seconds': { '{}': 500 },
          'llamacpp:predicted_tokens_seconds': { '{}': 60 },
          'llamacpp:requests_processing': { '{}': 0 },
          'llamacpp:requests_deferred': { '{}': 0 },
        },
        engine: 'llamacpp',
        scraped_at: '2026-01-01T00:00:00Z'
      },
      slots: new Error('404')
    })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'llamacpp-test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    const firstPoint = result.current.history[0]
    expect(firstPoint.promptTokensRate).toBe(0)
    expect(firstPoint.generationTokensRate).toBe(0)
  })

  it('running/waiting counts still map from metrics while rates come from slots', async () => {
    queueLlamaCpp({
      metrics: {
        metrics: {
          ...llamacppMetricsBase.metrics,
          'llamacpp:requests_processing': { '{}': 2 },
          'llamacpp:requests_deferred': { '{}': 1 },
        },
        engine: 'llamacpp',
        scraped_at: '2026-01-01T00:00:00Z'
      },
      slots: slotsPayload([{ id: 0, is_processing: true, id_task: 100, n_decoded: 100, n_prompt_tokens: 500, n_prompt_tokens_processed: 500 }])
    })
    const { result } = renderHook(() => useServiceMetrics({ serviceName: 'llamacpp-test', enabled: true }))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.history[0].running).toBe(2)
    expect(result.current.history[0].waiting).toBe(1)
  })
})
})
