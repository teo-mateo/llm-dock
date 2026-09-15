import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup, within, act } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import BenchmarkTab from './BenchmarkTab'
import ServiceDetailsPage from './ServiceDetailsPage'

const { fetchAPIMock, serviceDetailsMock } = vi.hoisted(() => ({
  fetchAPIMock: vi.fn(),
  serviceDetailsMock: vi.fn(),
}))

vi.mock('../api', () => ({ fetchAPI: (...a) => fetchAPIMock(...a) }))
vi.mock('../hooks/useServicesSSE', () => ({
  default: () => ({ services: [], loading: false, error: null, connected: true, refresh: vi.fn() }),
}))
vi.mock('../hooks/useServiceDetails', () => ({ default: (...a) => serviceDetailsMock(...a) }))

const SERVICE = 'llamacpp-x'

const BENCH_ONLY = ['-m', '-o', '-p', '-n', '-r', '-pg', '-d', '-oe', '-v', '--delay', '--list-devices']

function routeFetch() {
  fetchAPIMock.mockImplementation((endpoint, options = {}) => {
    const method = options.method || 'GET'
    if (endpoint === `/benchmarks/service-defaults/${SERVICE}`) {
      return Promise.resolve({ params: { '-p': '512', '-n': '128', '-r': '5', '-ngl': '99' } })
    }
    if (endpoint === '/benchmarks/bench-only-flags') {
      return Promise.resolve({ flags: BENCH_ONLY })
    }
    if (endpoint.startsWith('/benchmarks?')) {
      return Promise.resolve({ runs: [COMPLETED_RUN], total: 1, limit: 50, offset: 0 })
    }
    if (endpoint === `/benchmarks/${COMPLETED_RUN.id}`) {
      return Promise.resolve(COMPLETED_RUN)
    }
    if (endpoint === '/benchmarks' && method === 'POST') {
      return Promise.resolve({ id: 'run-active', service_name: SERVICE, status: 'pending', message: 'Benchmark queued' })
    }
    if (endpoint === `/benchmarks/run-active`) {
      return Promise.resolve(RUNNING_RUN)
    }
    if (endpoint === `/benchmarks/${COMPLETED_RUN.id}/apply` && method === 'PUT') {
      return Promise.resolve({
        success: true,
        message: 'Configuration applied to llamacpp-x. Restart the service for changes to take effect.',
        applied_params: { '-ngl': '99' },
        skipped_flags: ['-p', '-n', '-r'],
      })
    }
    return Promise.resolve({})
  })
}

const COMPLETED_RUN = {
  id: 'run-done-1234',
  service_name: SERVICE,
  model_path: '/models/x.gguf',
  status: 'completed',
  params: { '-p': '512', '-n': '128', '-r': '5', '-ngl': '99' },
  pp_avg_ts: 410.2,
  pp_stddev_ts: 1.1,
  tg_avg_ts: 24.7,
  tg_stddev_ts: 0.4,
  raw_output: 'pp64  409 t/s',
  error_message: null,
  created_at: '2026-09-15T08:00:00Z',
  started_at: '2026-09-15T08:00:01Z',
  completed_at: '2026-09-15T08:01:00Z',
}

const RUNNING_RUN = { ...COMPLETED_RUN, id: 'run-active', status: 'running', raw_output: null, completed_at: null }

const RUNNING_COMPLETED = { ...RUNNING_RUN, status: 'completed', pp_avg_ts: COMPLETED_RUN.pp_avg_ts, tg_avg_ts: COMPLETED_RUN.tg_avg_ts, completed_at: '2026-09-15T08:05:00Z' }

function renderTab() {
  return render(<BenchmarkTab serviceName={SERVICE} modelPath="/models/x.gguf" />)
}

beforeEach(() => {
  fetchAPIMock.mockReset()
  fetchAPIMock.mockResolvedValue({})
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('BenchmarkTab', () => {
  it('prefills params from the service defaults and lists history', async () => {
    routeFetch()
    renderTab()

    await waitFor(() => expect(screen.getByDisplayValue('512')).toBeInTheDocument())
    // The service's own -ngl flag rides in the prefill
    expect(screen.getByDisplayValue('99')).toBeInTheDocument()
    // Command preview carries the prefilled flags
    await waitFor(() => expect(screen.getByText(/llama-bench -m .*\.gguf/)).toBeInTheDocument())
    // History row renders
    expect(screen.getByText('410.20 t/s')).toBeInTheDocument()
    expect(screen.getByText('Apply to service')).toBeInTheDocument()
    // The fetched set badges the bench minimums, not the service's own flag
    await waitFor(() => expect(screen.getAllByText('bench')).toHaveLength(3))
  })

  it('starts a run, shows the live status, and settles on completion', async () => {
    let polls = 0
    fetchAPIMock.mockImplementation((endpoint, options = {}) => {
      if (endpoint === `/benchmarks/run-active`) {
        polls += 1
        return Promise.resolve(polls >= 2 ? RUNNING_COMPLETED : RUNNING_RUN)
      }
      if (endpoint === '/benchmarks' && options.method === 'POST') {
        return Promise.resolve({ id: 'run-active', service_name: SERVICE, status: 'pending', message: 'Benchmark queued' })
      }
      if (endpoint === `/benchmarks/service-defaults/${SERVICE}`) {
        return Promise.resolve({ params: { '-p': '512', '-n': '128', '-r': '5' } })
      }
      if (endpoint.startsWith('/benchmarks?')) {
        return Promise.resolve({ runs: [COMPLETED_RUN], total: 1 })
      }
      return Promise.resolve({})
    })

    renderTab()
    await waitFor(() => expect(screen.getByRole('button', { name: /Start benchmark/i })).toBeEnabled())

    fireEvent.click(screen.getByRole('button', { name: /Start benchmark/i }))

    // POST with the prefill as params
    await waitFor(() => {
      const post = fetchAPIMock.mock.calls.find(c => c[0] === '/benchmarks' && c[1]?.method === 'POST')
      expect(post).toBeTruthy()
      expect(JSON.parse(post[1].body)).toEqual({
        service_name: SERVICE,
        params: { '-p': '512', '-n': '128', '-r': '5' },
      })
    })

    // Live status card: the Cancel button is present from the moment the
    // POST lands (pending or running), so it is stable across the poll cycle.
    await screen.findByRole('button', { name: /Cancel/i })

    // The poll interval (2 s) settles the run; the stddev suffix only exists
    // on the status card, not the history table, so it is unambiguous.
    await screen.findByText(/\(±0\.40\)/, {}, { timeout: 10000 })
  }, 20000)

  it('applies a completed run with the confirmation, showing what was applied and skipped', async () => {
    routeFetch()
    renderTab()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Apply to service' })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Apply to service' }))

    await waitFor(() => {
      const put = fetchAPIMock.mock.calls.find(c => c[0] === `/benchmarks/${COMPLETED_RUN.id}/apply` && c[1]?.method === 'PUT')
      expect(put).toBeTruthy()
    })
    expect(window.confirm).toHaveBeenCalled()
    const banner = await screen.findByText('Configuration applied').then(el => el.closest('.rounded-lg'))
    await screen.findByText(/Restart the service for changes to take effect\./)
    // The command preview also carries '-ngl 99', so scope to the banner.
    expect(within(banner).getByText(/-ngl 99/)).toBeInTheDocument()
    expect(screen.getByText(/Skipped \(benchmark-only\): -p, -n, -r/)).toBeInTheDocument()
  })

  it('surfaces a start failure and refreshes the history so an existing run is visible', async () => {
    fetchAPIMock.mockImplementation((endpoint, options = {}) => {
      if (endpoint === '/benchmarks' && options.method === 'POST') {
        return Promise.reject(new Error('Benchmark already running for llamacpp-x'))
      }
      if (endpoint === `/benchmarks/service-defaults/${SERVICE}`) {
        return Promise.resolve({ params: {} })
      }
      if (endpoint.startsWith('/benchmarks?')) {
        return Promise.resolve({ runs: [{ ...COMPLETED_RUN, id: 'run-active', status: 'running' }], total: 1 })
      }
      return Promise.resolve({})
    })
    renderTab()
    await waitFor(() => expect(screen.getByRole('button', { name: /Start benchmark/i })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: /Start benchmark/i }))

    await waitFor(() => expect(screen.getByText('Benchmark already running for llamacpp-x')).toBeInTheDocument())
    // The running run is surfaced in the history
    await waitFor(() => expect(screen.getAllByText('running').length).toBeGreaterThan(0))
  })

  it('drops the live card when the cancel DELETE 404s (the row vanished mid-click)', async () => {
    fetchAPIMock.mockImplementation((endpoint, options = {}) => {
      if (endpoint === `/benchmarks/run-active` && options.method === 'DELETE') {
        return Promise.reject(new Error('Benchmark run not found'))
      }
      if (endpoint === `/benchmarks/run-active`) {
        return Promise.resolve(RUNNING_RUN)
      }
      if (endpoint === '/benchmarks' && options.method === 'POST') {
        return Promise.resolve({ id: 'run-active', service_name: SERVICE, status: 'pending' })
      }
      if (endpoint === `/benchmarks/service-defaults/${SERVICE}`) {
        return Promise.resolve({ params: {} })
      }
      if (endpoint.startsWith('/benchmarks?')) {
        return Promise.resolve({ runs: [] })
      }
      return Promise.resolve({})
    })
    renderTab()
    const start = await screen.findByRole('button', { name: /Start benchmark/i })
    fireEvent.click(start)
    const cancel = await screen.findByRole('button', { name: /Cancel/i })

    await act(async () => { fireEvent.click(cancel) })

    // The live card is gone (no stale 'running' state) and the history
    // refreshed - and the rejection did not escape.
    expect(screen.queryByRole('button', { name: /Cancel/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Start benchmark/i })).toBeEnabled()
    expect(fetchAPIMock.mock.calls.filter(c => c[0].startsWith('/benchmarks?')).length).toBeGreaterThan(1)
  })
})

describe('ServiceDetailsPage benchmark gating', () => {
  it('shows the Benchmark tab only for llamacpp services', async () => {
    // The page and its children carry config in effect deps — the mock must
    // return stable references, or every render re-runs them into a loop.
    const mocks = {}
    serviceDetailsMock.mockImplementation((name) => {
      if (!mocks[name]) {
        mocks[name] = {
          config: { template_type: name === 'vllm-x' ? 'vllm' : 'llamacpp', model_path: '/m.gguf' },
          runtime: { status: 'running' },
          loading: false,
          error: null,
          transitioning: false,
          refetchConfig: vi.fn(),
          actions: { start: vi.fn(), stop: vi.fn(), restart: vi.fn(), rename: vi.fn(), deleteService: vi.fn(), setPublicPort: vi.fn(), fetchYamlPreview: vi.fn(), registerOpenWebUI: vi.fn(), unregisterOpenWebUI: vi.fn() },
        }
      }
      return mocks[name]
    })

    const renderPage = (name, path) => render(
      <MemoryRouter initialEntries={[`/services/${name}${path}`]}>
        <Routes>
          <Route path="/services/:serviceName/*" element={<ServiceDetailsPage />} />
        </Routes>
      </MemoryRouter>
    )

    const llamacpp = renderPage('llamacpp-x', '')
    expect(llamacpp.getByText('Benchmark')).toBeInTheDocument()
    cleanup()

    const vllm = renderPage('vllm-x', '')
    expect(vllm.queryByText('Benchmark')).not.toBeInTheDocument()
  })
})
