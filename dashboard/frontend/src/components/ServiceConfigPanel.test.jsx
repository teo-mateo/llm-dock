import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import ServiceConfigPanel from './ServiceConfigPanel'

const { fetchAPIMock, refreshMock } = vi.hoisted(() => ({
  fetchAPIMock: vi.fn(),
  refreshMock: vi.fn(),
}))

vi.mock('../api', () => ({ fetchAPI: (...a) => fetchAPIMock(...a) }))
vi.mock('../hooks/useServicesSSE', () => ({
  default: () => ({ services: [], loading: false, error: null, connected: true, refresh: refreshMock }),
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
  refreshMock.mockReset()
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

  it('refreshes the service snapshot so chat sees the new ladder', async () => {
    setup({ ...BASE, reasoning_levels: 'off' })
    fireEvent.change(input(), { target: { value: 'off,low' } })
    fireEvent.click(screen.getByRole('button', { name: /^Save/ }))
    await waitFor(() => expect(refreshMock).toHaveBeenCalled())
  })

  it('does not refresh the snapshot when the server rejects the grammar', async () => {
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
    expect(refreshMock).not.toHaveBeenCalled()
  })
})
