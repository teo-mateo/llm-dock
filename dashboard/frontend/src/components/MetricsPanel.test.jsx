import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import MetricsPanel from './MetricsPanel'

vi.mock('../api', () => ({
  fetchAPI: vi.fn()
}))

vi.mock('../hooks/useServiceMetrics', () => ({
  __esModule: true,
  default: vi.fn()
}))

import useServiceMetrics from '../hooks/useServiceMetrics'

afterEach(cleanup)

describe('MetricsPanel', () => {
  it('reports SGLang pool capacity separately from active and cached slots', () => {
    useServiceMetrics.mockReturnValue({ engine: 'sglang', metrics: {
      'sglang:max_total_num_tokens': { '{}': 200000 },
      'sglang:kv_used_tokens': { '{}': 64 },
      'sglang:kv_evictable_tokens': { '{}': 1200 },
      'sglang:kv_available_tokens': { '{}': 198736 },
      'sglang:mamba_used_tokens': { '{}': 2 },
      'sglang:mamba_evictable_tokens': { '{}': 8 },
      'sglang:mamba_available_tokens': { '{}': 20 },
      'sglang:hicache_host_used_tokens': { '{}': 5000 },
      'sglang:hicache_host_total_tokens': { '{}': 679296 },
      'sglang:spec_accept_length': { '{}': 2.825 },
      'sglang:graph_memory_usage_gb': { 'phase=prefill': 0, 'phase=target_verify': 0.36, 'phase=draft_decode': 0.34 },
    }, history: [{}], loading: false, error: null })
    render(<MetricsPanel serviceName="sglang-next" enabled />)
    expect(screen.getByText('KV tokens')).toBeInTheDocument()
    expect(screen.getByText('Mamba state slots')).toBeInTheDocument()
    expect(screen.getByText('200,000')).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
    expect(screen.getByText('679,296')).toBeInTheDocument()
    expect(screen.getByText('2.83')).toBeInTheDocument()
    expect(screen.getByText('0.7')).toBeInTheDocument()
  })
  it('shows no metrics available when metrics empty and no history', () => {
    useServiceMetrics.mockReturnValue({
      metrics: {},
      history: [],
      loading: false,
      error: null,
      lastScraped: null
    })
    render(<MetricsPanel serviceName="test" enabled={true} />)
    expect(screen.getByText('No metrics available')).toBeTruthy()
  })

  it('renders all sub-panels when metrics present', () => {
    useServiceMetrics.mockReturnValue({
      metrics: {
        'vllm:kv_cache_usage_perc': { 'gpu_id=0': 0.7 },
        'vllm:num_requests_running': { '{}': 2 },
        'vllm:num_requests_waiting': { '{}': 0 }
      },
      history: [
        {
          promptTokensRate: 10,
          generationTokensRate: 20,
          kvCache: 0.7,
          prefixHitRatio: 0.8,
          specAcceptRatio: 0.5,
          running: 2,
          waiting: 0,
          preemptRate: 0
        }
      ],
      loading: false,
      error: null,
      lastScraped: new Date().toISOString()
    })
    render(<MetricsPanel serviceName="test" enabled={true} />)
    expect(screen.getByText('Requests')).toBeTruthy()
    expect(screen.getByText('Token Throughput')).toBeTruthy()
    expect(screen.getByText('Utilization')).toBeTruthy()
    expect(screen.getByText('Active KV')).toBeTruthy()
  })

  it('shows disabled state when enabled is false', () => {
    useServiceMetrics.mockReturnValue({
      metrics: {},
      history: [],
      loading: false,
      error: null,
      lastScraped: null
    })
    render(<MetricsPanel serviceName="test" enabled={false} />)
    expect(screen.getByText('(disabled)')).toBeTruthy()
  })

  it('shows error message when error present', () => {
    useServiceMetrics.mockReturnValue({
      metrics: {},
      history: [],
      loading: false,
      error: 'Connection refused',
      lastScraped: null
    })
    render(<MetricsPanel serviceName="test" enabled={true} />)
    expect(screen.getByText('Connection refused')).toBeTruthy()
  })
})
