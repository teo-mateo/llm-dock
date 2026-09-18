import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import InspectToggleCard from './InspectToggleCard'

const { fetchAPIMock, setInspectMock } = vi.hoisted(() => ({
  fetchAPIMock: vi.fn(),
  setInspectMock: vi.fn(),
}))

vi.mock('../api', () => ({
  fetchAPI: (...a) => fetchAPIMock(...a),
  setServiceInspect: (...a) => setInspectMock(...a),
}))

const NAME = 'llamacpp-x'

function setup({
  config = {},
  runtime = { status: 'not-created' },
  services = [],
} = {}) {
  const onSaved = vi.fn()
  const onError = vi.fn()
  fetchAPIMock.mockReset()
  fetchAPIMock.mockImplementation((path) =>
    path === '/inspector/services'
      ? Promise.resolve({ services })
      : Promise.resolve({})
  )
  setInspectMock.mockReset()
  const view = render(
    <MemoryRouter>
      <InspectToggleCard
        config={config}
        runtime={runtime}
        serviceName={NAME}
        onSaved={onSaved}
        onError={onError}
      />
    </MemoryRouter>
  )
  return { view, onSaved, onError }
}

const OFF_CONFIG = { inspect: false, port: 3317 }
const ON_CONFIG = { inspect: true, port: 3317, inspect_upstream_port: 34001 }
const LIVE_SERVICE = {
  service_name: NAME,
  capture_count: 91,
  inspect: true,
  listen_port: 3317,
  upstream_port: 34001,
  proxy_running: true,
  error: null,
}

afterEach(() => {
  cleanup()
  fetchAPIMock.mockReset()
  setInspectMock.mockReset()
})

describe('InspectToggleCard', () => {
  it('renders the OFF copy for inspect: false and for an absent field', () => {
    for (const config of [{ ...OFF_CONFIG }, { port: 3317 }]) {
      const { view } = setup({ config })
      expect(screen.getByText('Request inspection')).toBeTruthy()
      expect(
        screen.getByText(
          'Off — requests go straight to the container. Turn this on to record every payload sent to this model: system prompt, messages, tool definitions and the response.'
        )
      ).toBeTruthy()
      expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
      view.unmount()
    }
  })

  it('renders both ports, the proxy state and the capture count when ON', async () => {
    setup({
      config: ON_CONFIG,
      runtime: { status: 'running', host_port: 3317 },
      services: [LIVE_SERVICE],
    })

    expect(screen.getByText('clients keep this URL')).toBeTruthy()
    expect(screen.getByText('loopback only')).toBeTruthy()
    expect(screen.getByText('127.0.0.1:34001')).toBeTruthy()
    await waitFor(() => expect(screen.getByText('Running')).toBeTruthy())
    await waitFor(() => expect(screen.getByText('91 recorded')).toBeTruthy())
    const link = screen.getByText('View in Inspector')
    expect(link.getAttribute('href')).toContain('/inspector?service=llamacpp-x')
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
  })

  it('shows the recreate confirm for a running service; Cancel fires no request', async () => {
    setup({
      config: OFF_CONFIG,
      runtime: { status: 'running', host_port: 3317 },
    })

    fireEvent.click(screen.getByRole('switch'))
    expect(screen.getByText('Recreate llamacpp-x now?')).toBeTruthy()
    expect(setInspectMock).not.toHaveBeenCalled()

    fireEvent.click(screen.getByText('Cancel'))
    expect(screen.queryByText('Recreate llamacpp-x now?')).toBeNull()
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    expect(setInspectMock).not.toHaveBeenCalled()
  })

  it('confirms with Enable then fires the request for a running service', async () => {
    const { onSaved } = setup({
      config: OFF_CONFIG,
      runtime: { status: 'running', host_port: 3317 },
    })
    setInspectMock.mockResolvedValue({
      proxy_running: true, error: null, port: 3317, upstream_port: 34000, restarted: true,
    })

    fireEvent.click(screen.getByRole('switch'))
    fireEvent.click(screen.getByText('Enable'))

    expect(setInspectMock).toHaveBeenCalledTimes(1)
    expect(setInspectMock).toHaveBeenCalledWith(NAME, true)
    await waitFor(() =>
      expect(onSaved).toHaveBeenCalledWith(
        'Inspection enabled — clients keep using port 3317 (container restarted)'
      )
    )
  })

  it('fires immediately with no confirm for a stopped service', async () => {
    const { onSaved } = setup({ config: OFF_CONFIG })
    setInspectMock.mockResolvedValue({
      proxy_running: true, error: null, port: 3317, upstream_port: 34000, restarted: false,
    })

    fireEvent.click(screen.getByRole('switch'))

    expect(screen.queryByText('Recreate llamacpp-x now?')).toBeNull()
    expect(setInspectMock).toHaveBeenCalledTimes(1)
    expect(setInspectMock).toHaveBeenCalledWith(NAME, true)
    await waitFor(() =>
      expect(onSaved).toHaveBeenCalledWith('Inspection enabled — clients keep using port 3317')
    )
  })

  it('a second click while busy sends no second request', async () => {
    setup({ config: OFF_CONFIG })
    setInspectMock.mockReturnValue(new Promise(() => {}))

    fireEvent.click(screen.getByRole('switch'))

    expect(setInspectMock).toHaveBeenCalledTimes(1)
    // The switch is replaced by the spinner; there is nothing left to click,
    // so a second request cannot be started.
    expect(screen.queryByRole('switch')).toBeNull()
    expect(screen.getByText('Enabling…')).toBeTruthy()
    expect(setInspectMock).toHaveBeenCalledTimes(1)
  })

  it('reverts the toggle and shows a danger toast on a failed request', async () => {
    const { onSaved, onError } = setup({ config: OFF_CONFIG })
    setInspectMock.mockRejectedValue(new Error('Server said no'))

    fireEvent.click(screen.getByRole('switch'))

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Server said no'))
    expect(onSaved).not.toHaveBeenCalled()
    expect(setInspectMock).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
  })

  it('renders the red banner and a working Retry when the proxy did not bind', async () => {
    setup({
      config: ON_CONFIG,
      runtime: { status: 'running', host_port: 3317 },
      services: [
        {
          ...LIVE_SERVICE,
          proxy_running: false,
          error: '[Errno 98] Address already in use',
        },
      ],
    })
    setInspectMock.mockResolvedValue({
      proxy_running: true, error: null, port: 3317, upstream_port: 34001, restarted: false,
    })

    await waitFor(() =>
      expect(
        screen.getByText('Proxy failed to bind port 3317: [Errno 98] Address already in use')
      ).toBeTruthy()
    )

    fireEvent.click(screen.getByText('Retry'))
    expect(setInspectMock).toHaveBeenCalledTimes(1)
    expect(setInspectMock).toHaveBeenCalledWith(NAME, true)
  })

  it('shows the recreate warning whenever the service is running', () => {
    setup({ config: OFF_CONFIG, runtime: { status: 'running' } })
    expect(
      screen.getByText('Toggling recreates the container. In-flight requests will fail.')
    ).toBeTruthy()
    cleanup()

    setup({ config: ON_CONFIG, runtime: { status: 'running' } })
    expect(
      screen.getByText('Toggling recreates the container. In-flight requests will fail.')
    ).toBeTruthy()
    cleanup()

    setup({ config: OFF_CONFIG })
    expect(
      screen.queryByText('Toggling recreates the container. In-flight requests will fail.')
    ).toBeNull()
  })

  it('always shows the footnote, in both states', () => {
    setup({ config: OFF_CONFIG })
    expect(screen.getByText(/Captures every client that reaches this port/)).toBeTruthy()
    cleanup()

    setup({ config: ON_CONFIG })
    expect(screen.getByText(/Captures every client that reaches this port/)).toBeTruthy()
  })

  it('exposes a keyboard-operable switch (native button) with role and aria-checked', () => {
    setup({ config: OFF_CONFIG })
    const sw = screen.getByRole('switch')
    expect(sw.tagName).toBe('BUTTON')
    expect(sw).toHaveAttribute('aria-checked', 'false')
    expect(sw).toHaveAttribute('aria-label', `Toggle request inspection for ${NAME}`)
  })

  it('hides the Captures row when the inspector/services call fails', async () => {
    fetchAPIMock.mockRejectedValue(new Error('down'))
    setup({
      config: ON_CONFIG,
      runtime: { status: 'running', host_port: 3317 },
    })

    // The card still renders its full ON state from config alone.
    await waitFor(() => expect(screen.getByText('127.0.0.1:34001')).toBeTruthy())
    expect(screen.queryByText('Captures')).toBeNull()
    expect(screen.queryByText(/recorded/)).toBeNull()
  })

  it('hides the banner when the fetch reports the proxy is running', async () => {
    setup({
      config: ON_CONFIG,
      runtime: { status: 'running', host_port: 3317 },
      services: [LIVE_SERVICE],
    })

    await waitFor(() => expect(screen.getByText('Running')).toBeTruthy())
    expect(screen.queryByText(/Proxy failed to bind/)).toBeNull()
  })
})
