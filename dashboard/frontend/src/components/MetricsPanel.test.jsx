import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import MetricsPanel from './MetricsPanel'

vi.mock('../api', () => ({
  fetchAPI: vi.fn()
}))

vi.mock('../hooks/useServiceMetrics', () => ({
  __esModule: true,
  default: vi.fn()
}))

import useServiceMetrics from '../hooks/useServiceMetrics'

describe('MetricsPanel', () => {
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
    expect(screen.getByText('KV Cache')).toBeTruthy()
  })

  it('render green pulse dot when polling active', () => {
    useServiceMetrics.mockReturnValue({
      metrics: { 'vllm:kv_cache_usage_perc': { 'gpu_id=0': 0.5 } },
      history: [{ kvCache: 0.5, running: 0, waiting: 0, preemptRate: 0, promptTokensRate: 0, generationTokensRate: 0 }],
      loading: false,
      error: null,
      lastScraped: new Date().toISOString()
    })
    const { container } = render(<MetricsPanel serviceName="test" enabled={true} />)
    const dot = container.querySelector('.bg-green-500')
    expect(dot).toBeTruthy()
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

  it('shows red dot and error message when error present', () => {
    useServiceMetrics.mockReturnValue({
      metrics: {},
      history: [],
      loading: false,
      error: 'Connection refused',
      lastScraped: null
    })
    const { container } = render(<MetricsPanel serviceName="test" enabled={true} />)
    expect(container.querySelector('.bg-red-500')).toBeTruthy()
    expect(screen.getByText('Connection refused')).toBeTruthy()
  })
})
