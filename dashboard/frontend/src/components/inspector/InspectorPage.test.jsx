import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { MemoryRouter, useSearchParams } from 'react-router-dom'
import InspectorPage from './InspectorPage'

const { listMock, servicesMock, getMock, deleteAllMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
  servicesMock: vi.fn(),
  getMock: vi.fn(),
  deleteAllMock: vi.fn(),
}))

vi.mock('../../services/inspector', () => ({
  listCaptures: (opts) => listMock(opts),
  inspectorServices: () => servicesMock(),
  getCapture: (id) => getMock(id),
  deleteCaptures: (service) => deleteAllMock(service),
}))

function row(id, model, serviceName) {
  return {
    id,
    service_name: serviceName,
    model,
    template_type: 'llamacpp',
    method: 'POST',
    path: '/v1/chat/completions',
    status_code: 200,
    stream: true,
    prompt_tokens: 10,
    completion_tokens: 5,
    total_tokens: 15,
    ttfb_ms: 100,
    duration_ms: 2000,
    error: null,
    request_truncated: false,
    response_truncated: false,
    created_at: new Date(Date.now() - 60000).toISOString(),
  }
}

function captureDetail(id, model, content) {
  return {
    ...row(id, model, 'svc-a'),
    request_headers: { Authorization: '***redacted***' },
    request_body: JSON.stringify({ model, messages: [{ role: 'user', content }] }),
    response_body: 'data: [DONE]\n\n',
    response_text: content,
    reasoning_text: null,
    tool_calls: [],
    finish_reason: 'stop',
  }
}

function ParamsProbe() {
  const [params] = useSearchParams()
  return <span data-testid="probe">{params.toString()}</span>
}

function renderPage(entry = '/inspector') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <InspectorPage />
      <ParamsProbe />
    </MemoryRouter>
  )
}

beforeEach(() => {
  listMock.mockReset()
  servicesMock.mockReset()
  getMock.mockReset()
  deleteAllMock.mockReset()

  listMock.mockImplementation(({ service }) =>
    service === 'svc-b'
      ? Promise.resolve({ captures: [row('c2', 'model-b', 'svc-b')], total: 1, limit: 50, offset: 0 })
      : Promise.resolve({ captures: [row('c1', 'model-a', 'svc-a'), row('c2', 'model-b', 'svc-b')], total: 137, limit: 50, offset: 0 })
  )
  servicesMock.mockResolvedValue({
    services: [
      { service_name: 'svc-a', capture_count: 136, inspect: true, listen_port: 3317, upstream_port: 34000, proxy_running: true, error: null },
      { service_name: 'svc-b', capture_count: 1, inspect: true, listen_port: 3318, upstream_port: 34001, proxy_running: true, error: null },
    ],
  })
  getMock.mockImplementation((id) =>
    id === 'c1'
      ? Promise.resolve(captureDetail('c1', 'model-a', 'first message'))
      : id === 'c2'
        ? Promise.resolve(captureDetail('c2', 'model-b', 'second message'))
        : Promise.reject(new Error('404'))
  )
  deleteAllMock.mockResolvedValue({ deleted: 137 })
})

afterEach(cleanup)

describe('InspectorPage shell', () => {
  it('renders the header, filter, live switch, refresh and delete-all controls', async () => {
    renderPage()
    expect(screen.getByRole('heading', { name: 'Inspector' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('model-a')).toBeInTheDocument())
    expect(screen.getByRole('switch', { name: 'Live updates' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('button', { name: /Refresh/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete all' })).toBeInTheDocument()
    expect(screen.getByRole('combobox')).toHaveValue('')
    expect(screen.getByRole('option', { name: 'All services (137)' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'svc-b (1)' })).toBeInTheDocument()
  })

  it('prompts for a selection while none is active', () => {
    renderPage()
    expect(screen.getByText('Select a capture to inspect it.')).toBeInTheDocument()
  })

  it('toggling Live flips the switch', () => {
    renderPage()
    fireEvent.click(screen.getByRole('switch', { name: 'Live updates' }))
    expect(screen.getByRole('switch', { name: 'Live updates' })).toHaveAttribute('aria-checked', 'false')
  })
})

describe('InspectorPage url state', () => {
  it('honours ?service= on load: filtered fetch, selected option, scoped delete label', async () => {
    renderPage('/inspector?service=svc-b')

    await waitFor(() => expect(screen.getByText('model-b')).toBeInTheDocument())
    expect(listMock).toHaveBeenCalledWith({ service: 'svc-b', limit: 50, offset: 0 })
    expect(screen.getByRole('combobox')).toHaveValue('svc-b')
    expect(screen.getByRole('button', { name: 'Delete all for svc-b' })).toBeInTheDocument()
  })

  it('selecting a row writes ?capture= and loads the detail', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('model-a')).toBeInTheDocument())

    fireEvent.click(screen.getByText('model-a'))
    await waitFor(() => expect(getMock).toHaveBeenCalledWith('c1'))
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toContain('capture=c1'))
    expect(screen.getByText('first message')).toBeInTheDocument()
  })

  it('honours ?capture= on load', async () => {
    renderPage('/inspector?capture=c2')
    await waitFor(() => expect(screen.getByText('second message')).toBeInTheDocument())
  })

  it('changing the filter rewrites the query and drops the capture', async () => {
    renderPage('/inspector?capture=c1')
    await waitFor(() => expect(screen.getByText('first message')).toBeInTheDocument())

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'svc-b' } })
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('service=svc-b'))
  })

  it('a deleted capture 404s, clears the selection and says so', async () => {
    renderPage('/inspector?capture=gone')
    await waitFor(() => expect(screen.getByText('This capture no longer exists.')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe(''))
  })
})

describe('InspectorPage deletion', () => {
  it('Delete all asks with the count, and the confirm empties the list', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('model-a')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Delete all' }))
    expect(screen.getByText('Delete 137 captures? This cannot be undone.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(deleteAllMock).not.toHaveBeenCalled()
    expect(screen.queryByText('model-a')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Delete all' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    listMock.mockResolvedValue({ captures: [], total: 0, limit: 50, offset: 0 })

    await waitFor(() => expect(deleteAllMock).toHaveBeenCalledWith(null))
    await waitFor(() => expect(screen.getByText('No captures yet.')).toBeInTheDocument())
  })
})

describe('InspectorPage detail behaviour', () => {
  it('selecting a different capture resets the sub-tab to Conversation', async () => {
    renderPage('/inspector?capture=c1')
    await waitFor(() => expect(screen.getByText('first message')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Request' }))
    expect(screen.getByText(/Raw request body/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('model-b'))
    await waitFor(() => expect(screen.getByText('second message')).toBeInTheDocument())
    expect(screen.queryByText(/Raw request body/)).not.toBeInTheDocument()
  })

  it('re-selecting a capture serves the cache without refetching', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('model-a')).toBeInTheDocument())

    fireEvent.click(screen.getByText('model-a'))
    await waitFor(() => expect(screen.getByText('first message')).toBeInTheDocument())
    const calls = getMock.mock.calls.length

    fireEvent.click(screen.getByText('model-b'))
    await waitFor(() => expect(screen.getByText('second message')).toBeInTheDocument())
    fireEvent.click(screen.getByText('model-a'))
    await waitFor(() => expect(screen.getByText('first message')).toBeInTheDocument())

    expect(getMock.mock.calls.length).toBe(calls + 1)
  })
})
