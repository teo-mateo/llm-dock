import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import ServiceConfigPanel from './ServiceConfigPanel'

const { fetchAPIMock, sseHookCalls } = vi.hoisted(() => ({
  fetchAPIMock: vi.fn(),
  sseHookCalls: { count: 0 },
}))

vi.mock('../api', () => ({ fetchAPI: (...a) => fetchAPIMock(...a) }))
// The panel must not subscribe: every useServicesSSE() call is its own
// EventSource, so counting calls pins the absence rather than mocking a return.
vi.mock('../hooks/useServicesSSE', () => ({
  default: () => {
    sseHookCalls.count += 1
    return { services: [], loading: false, error: null, connected: true, refresh: vi.fn() }
  },
}))

const BASE = {
  template_type: 'llamacpp',
  port: 3345,
  api_key: 'k',
  params: { '-ngl': '99' },
  model_path: '/models/x.gguf',
  alias: 'llamacpp-x',
}

function setup(config) {
  fetchAPIMock.mockResolvedValue({})
  return render(
    <ServiceConfigPanel
      config={config}
      serviceName="llamacpp-x"
      runtime={{ status: 'running' }}
      onSaved={vi.fn()}
      onError={vi.fn()}
      flagMetadata={{}}
    />
  )
}

function input() {
  return screen.getByLabelText('Reasoning levels')
}

afterEach(() => {
  cleanup()
  fetchAPIMock.mockReset()
  sseHookCalls.count = 0
})

const STORAGE_KEY = 'llmdock.service-params.flag-column-width'

function stubGeometry(width) {
  const spy = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() => ({
    width, height: 24, top: 0, left: 0, right: width, bottom: 24, x: 0, y: 0, toJSON: () => ({}),
  }))
  return spy
}

describe('ServiceConfigPanel parameter-name divider', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.removeItem(STORAGE_KEY)
  })

  it('renders a vertical separator between the name and value fields', () => {
    stubGeometry(1000)
    setup(BASE)
    const divider = screen.getAllByRole('separator')[0]
    expect(divider).toHaveAttribute('aria-orientation', 'vertical')
    expect(divider).toHaveAccessibleName('Resize parameter name column')
  })

  it('widens the name column when the divider is dragged', () => {
    stubGeometry(1000)
    setup(BASE)
    const flag = screen.getByDisplayValue('-ngl')
    const divider = screen.getAllByRole('separator')[0]
    fireEvent.mouseDown(divider)
    fireEvent.mouseMove(window, { clientX: 400 })
    expect(localStorage.getItem(STORAGE_KEY)).toBe('400')
    expect(flag.style.width).toMatch(/px/)
    fireEvent.mouseUp(window)
  })

  it('resizes with the arrow keys and persists the width', () => {
    localStorage.setItem(STORAGE_KEY, '160')
    stubGeometry(1000)
    setup(BASE)
    const divider = screen.getAllByRole('separator')[0]
    fireEvent.keyDown(divider, { key: 'ArrowRight' })
    expect(localStorage.getItem(STORAGE_KEY)).toBe('170')
    fireEvent.keyDown(divider, { key: 'ArrowLeft' })
    expect(localStorage.getItem(STORAGE_KEY)).toBe('160')
  })

  it('never narrows the name column below its minimum', () => {
    localStorage.setItem(STORAGE_KEY, '160')
    stubGeometry(1000)
    setup(BASE)
    const divider = screen.getAllByRole('separator')[0]
    fireEvent.keyDown(divider, { key: 'ArrowLeft' })
    fireEvent.keyDown(divider, { key: 'ArrowLeft' })
    expect(localStorage.getItem(STORAGE_KEY)).toBe('140')
  })
})

describe('ServiceConfigPanel reasoning levels', () => {
  it('initializes the field from the stored declaration', () => {
    setup({ ...BASE, reasoning_levels: 'off,low,medium' })
    expect(input().value).toBe('off,low,medium')
  })

  it('starts empty for a service that declares nothing', () => {
    setup({ ...BASE })
    expect(input().value).toBe('')
  })

  it('treats an edit as a dirty change and Discard reverts it', () => {
    setup({ ...BASE, reasoning_levels: 'off,low' })
    fireEvent.change(input(), { target: { value: 'off,low,xhigh' } })
    expect(screen.getByText('Unsaved changes')).toBeTruthy()
    fireEvent.click(screen.getByText('Discard'))
    expect(input().value).toBe('off,low')
  })

  it('sends the declaration on save', async () => {
    setup({ ...BASE })
    fireEvent.change(input(), { target: { value: 'off, low, medium' } })
    fireEvent.click(screen.getByRole('button', { name: /^Save/ }))
    await waitFor(() => expect(fetchAPIMock).toHaveBeenCalled())
    const [, opts] = fetchAPIMock.mock.calls[0]
    const body = JSON.parse(opts.body)
    // Sent as typed (outer whitespace trimmed): spaces around commas are part
    // of the grammar and the server trims each entry itself.
    expect(body.reasoning_levels).toBe('off, low, medium')
    expect(body.template_type).toBe('llamacpp')
  })

  it('sends an empty string to clear, rather than omitting the key', async () => {
    setup({ ...BASE, reasoning_levels: 'off,low' })
    fireEvent.change(input(), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: /^Save/ }))
    await waitFor(() => expect(fetchAPIMock).toHaveBeenCalled())
    const body = JSON.parse(fetchAPIMock.mock.calls[0][1].body)
    expect(body.reasoning_levels).toBe('')
  })

  it('opens no services stream of its own, before or after saving', async () => {
    // The ladder reaches chat as the PUT's own SSE delta, not a second stream.
    setup({ ...BASE, reasoning_levels: 'off' })
    expect(sseHookCalls.count).toBe(0)
    fireEvent.change(input(), { target: { value: 'off,low' } })
    fireEvent.click(screen.getByRole('button', { name: /^Save/ }))
    await waitFor(() => expect(fetchAPIMock).toHaveBeenCalled())
    expect(sseHookCalls.count).toBe(0)
  })

  it('opens no services stream when the server rejects the grammar', async () => {
    fetchAPIMock.mockReset()
    fetchAPIMock.mockRejectedValue(new Error('Validation failed'))
    const onError = vi.fn()
    render(
      <ServiceConfigPanel
        config={{ ...BASE, reasoning_levels: 'off' }}
        serviceName="llamacpp-x"
        runtime={{ status: 'stopped' }}
        onSaved={vi.fn()}
        onError={onError}
        flagMetadata={{}}
      />
    )
    fireEvent.change(input(), { target: { value: 'low:512' } })
    fireEvent.click(screen.getByRole('button', { name: /^Save/ }))
    await waitFor(() => expect(onError).toHaveBeenCalled())
    expect(sseHookCalls.count).toBe(0)
  })
})
