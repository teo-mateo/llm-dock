import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import useServiceMetrics from './useServiceMetrics'

const mockMetrics = {
  'vllm:prompt_tokens_total': { '{}': 50000 },
  'vllm:generation_tokens_total': { '{}': 120000 },
  'vllm:kv_cache_usage_perc': { 'gpu_id=0': 0.72 },
  'vllm:prefix_cache_queries_total': { '{}': 1000 },
  'vllm:prefix_cache_hits_total': { '{}': 800 },
  'vllm:spec_decode_num_drafts_total': { '{}': 10000 },
  'vllm:spec_decode_num_accepted_tokens_total': { '{}': 5000 },
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
    mockFetchAPI.mockResolvedValueOnce({ metrics: mockMetrics, scraped_at: '2026-01-01T00:03:00Z' })
    await act(async () => {
      vi.advanceTimersByTime(3000)
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
})
