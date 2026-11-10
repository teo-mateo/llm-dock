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

describe('ServiceConfigPanel image override', () => {
  const OVERRIDE = { ...BASE, image_override: true, image: 'mine:1' }

  function renderPanel(config, { runtime = { status: 'running', image: 'llm-dock-llamacpp' }, response = {} } = {}) {
    fetchAPIMock.mockReset()
    fetchAPIMock.mockResolvedValue(response)
    const onSaved = vi.fn()
    const onError = vi.fn()
    render(
      <ServiceConfigPanel
        config={config}
        serviceName="llamacpp-x"
        runtime={runtime}
        onSaved={onSaved}
        onError={onError}
        flagMetadata={{}}
      />
    )
    return { onSaved, onError }
  }

  const imageInput = () => screen.getByLabelText('Image')
  const save = () => fireEvent.click(screen.getByRole('button', { name: /^Save/ }))
  const putBody = () => JSON.parse(fetchAPIMock.mock.calls[0][1].body)

  it('shows the field only when the engine honours an image', () => {
    renderPanel(OVERRIDE)
    expect(imageInput()).toBeTruthy()
    cleanup()

    renderPanel({ ...BASE, image_override: false })
    expect(screen.queryByLabelText('Image')).toBeNull()
    cleanup()

    renderPanel(BASE)
    expect(screen.queryByLabelText('Image')).toBeNull()
  })

  it('prefills the stored override and shows the effective image', () => {
    renderPanel(OVERRIDE)

    expect(imageInput().value).toBe('mine:1')
    expect(screen.getByText(/Currently: llm-dock-llamacpp/)).toBeTruthy()
  })

  it('uses the effective image as the placeholder when there is no override', () => {
    renderPanel({ ...BASE, image_override: true })

    expect(imageInput().value).toBe('')
    expect(imageInput().placeholder).toBe('llm-dock-llamacpp')
  })

  it('is dirty after an image change only, and Discard restores it', () => {
    renderPanel(OVERRIDE)
    expect(screen.getByRole('button', { name: /^Save/ }).disabled).toBe(true)

    fireEvent.change(imageInput(), { target: { value: 'mine:2' } })
    expect(screen.getByRole('button', { name: /^Save/ }).disabled).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: /Discard/ }))
    expect(imageInput().value).toBe('mine:1')
  })

  it('sends the trimmed image, and an empty string when cleared', async () => {
    renderPanel(OVERRIDE)
    fireEvent.change(imageInput(), { target: { value: '  mine:2  ' } })
    save()
    await waitFor(() => expect(fetchAPIMock).toHaveBeenCalled())
    expect(putBody().image).toBe('mine:2')

    cleanup()
    renderPanel(OVERRIDE)
    fireEvent.change(imageInput(), { target: { value: '' } })
    save()
    await waitFor(() => expect(fetchAPIMock).toHaveBeenCalled())
    expect(putBody().image).toBe('')
  })

  it('sends no image for an engine that does not honour one', async () => {
    renderPanel({ ...BASE, image_override: false })
    fireEvent.change(screen.getByLabelText('Reasoning levels'), { target: { value: 'off' } })
    save()
    await waitFor(() => expect(fetchAPIMock).toHaveBeenCalled())

    expect('image' in putBody()).toBe(false)
  })

  it('says the container was recreated when the server recreated it', async () => {
    const { onSaved } = renderPanel(OVERRIDE, { response: { restarted: true } })
    fireEvent.change(imageInput(), { target: { value: 'mine:2' } })
    save()

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith('Configuration saved. Container recreated.'))
  })

  it('reports a failed recreation as an error, not as applied', async () => {
    const { onSaved } = renderPanel(OVERRIDE, { response: { restarted: false, recreate_error: 'pull access denied' } })
    fireEvent.change(imageInput(), { target: { value: 'mine:2' } })
    save()

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(
      'Configuration saved, but the container was not recreated: pull access denied', 'error',
    ))
  })

  it('tells a running service with an unchanged image to restart instead of claiming a recreate', async () => {
    const { onSaved } = renderPanel(OVERRIDE, { response: { restarted: false } })
    fireEvent.change(screen.getByLabelText('Reasoning levels'), { target: { value: 'off' } })
    save()

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith('Configuration saved. Restart the service to apply changes.'))
  })

  it('keeps the plain message for a stopped service', async () => {
    const { onSaved } = renderPanel(OVERRIDE, { runtime: { status: 'exited' }, response: { restarted: false } })
    fireEvent.change(imageInput(), { target: { value: 'mine:2' } })
    save()

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith('Configuration saved.'))
  })
})
