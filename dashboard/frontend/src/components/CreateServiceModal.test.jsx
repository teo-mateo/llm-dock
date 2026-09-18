import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import CreateServiceModal from './CreateServiceModal'

const { fetchAPIMock, navigateMock } = vi.hoisted(() => ({
  fetchAPIMock: vi.fn(),
  navigateMock: vi.fn(),
}))

vi.mock('../api', () => ({ fetchAPI: (...a) => fetchAPIMock(...a) }))
vi.mock('react-router-dom', () => ({ useNavigate: () => navigateMock }))
vi.mock('./commandPreview', () => ({ renderCommandPreview: () => 'preview' }))
vi.mock('./ParameterReference', () => ({ default: () => null }))

const SERVICES = [
  { name: 'llamacpp-a', host_port: 3301 },
  { name: 'vllm-b', host_port: 3302 },
]

function mockApi(result) {
  fetchAPIMock.mockImplementation(async (endpoint, opts) => {
    if (endpoint === '/system/info') return { models: [] }
    if (endpoint.startsWith('/flag-metadata/')) return { optional_flags: {} }
    if (endpoint === '/services' && opts?.method === 'POST') return result
    return {}
  })
}

function setup(props = {}) {
  // Default stubs for the two read endpoints; a test that set an
  // implementation first (mockApi or custom) keeps it.
  if (!fetchAPIMock.getMockImplementation()) {
    fetchAPIMock.mockImplementation(async (endpoint) => {
      if (endpoint === '/system/info') return { models: [] }
      if (endpoint.startsWith('/flag-metadata/')) return { optional_flags: {} }
      throw new Error('unexpected fetchAPI call: ' + endpoint)
    })
  }
  return render(
    <CreateServiceModal
      services={SERVICES}
      onClose={vi.fn()}
      onCreated={vi.fn()}
      {...props}
    />
  )
}

function fillForm({ alias = 'test-model', modelPath = '/hf-cache/m.gguf' } = {}) {
  fireEvent.change(screen.getByLabelText(/Service alias/), { target: { value: alias } })
  fireEvent.change(screen.getByLabelText(/Model path \(container\)/), { target: { value: modelPath } })
}

afterEach(() => {
  cleanup()
  fetchAPIMock.mockReset()
  navigateMock.mockReset()
})

describe('CreateServiceModal', () => {
  it('defaults to llama.cpp with the next free port from the service list', () => {
    setup()
    expect(screen.getByRole('radio', { name: /^llama\.cpp/ }).checked).toBe(true)
    expect(screen.getByLabelText(/Port/).value).toBe('3303')
    expect(screen.getByLabelText(/Model path \(container\)/)).toBeTruthy()
  })

  it('switches the model field to a HuggingFace name for vLLM', () => {
    setup()
    fireEvent.click(screen.getByRole('radio', { name: /vLLM/ }))
    expect(screen.queryByLabelText(/Model path \(container\)/)).toBeNull()
    expect(screen.getByLabelText(/HuggingFace model/)).toBeTruthy()
  })

  it('previews the generated service name from the alias', () => {
    setup()
    fireEvent.change(screen.getByLabelText(/Service alias/), { target: { value: 'Foo Bar' } })
    expect(screen.getByText('llamacpp-foo-bar')).toBeTruthy()
  })

  it('switches the name preview with the engine prefix', () => {
    setup()
    fireEvent.change(screen.getByLabelText(/Service alias/), { target: { value: 'test' } })
    fireEvent.click(screen.getByRole('radio', { name: /TabbyAPI/ }))
    expect(screen.getByText('exl3-test')).toBeTruthy()
  })

  it('disables the create button while required fields are empty', () => {
    setup()
    expect(screen.getByRole('button', { name: /Create service/ }).disabled).toBe(true)
  })

  it('posts the payload for a file-based engine and omits an empty api key', async () => {
    mockApi({ service_name: 'llamacpp-test-model', port: 3303, api_key: 'key-gen', success: true })
    const onCreated = vi.fn()
    setup({ onCreated })
    fillForm()
    fireEvent.change(screen.getByPlaceholderText('-flag'), { target: { value: '-ngl' } })
    fireEvent.change(screen.getByPlaceholderText('value (empty = bare flag)'), { target: { value: '99' } })
    fireEvent.click(screen.getByRole('button', { name: /Create service/ }))

    await waitFor(() => expect(fetchAPIMock).toHaveBeenCalledWith('/services', expect.objectContaining({ method: 'POST' })))
    const [, opts] = fetchAPIMock.mock.calls.find(([ep, o]) => ep === '/services' && o?.method === 'POST')
    const body = JSON.parse(opts.body)
    expect(body).toEqual({
      template_type: 'llamacpp',
      alias: 'test-model',
      port: 3303,
      model_path: '/hf-cache/m.gguf',
      params: { '-ngl': '99' },
    })
    expect(body.api_key).toBeUndefined()
    expect(body.model_name).toBeUndefined()
    expect(onCreated).toHaveBeenCalledTimes(1)
  })

  it('posts model_name instead of model_path for vLLM and includes a typed key', async () => {
    mockApi({ service_name: 'vllm-model-x', port: 3303, api_key: 'key-typed', success: true })
    setup()
    fireEvent.click(screen.getByRole('radio', { name: /vLLM/ }))
    fireEvent.change(screen.getByLabelText(/Service alias/), { target: { value: 'model-x' } })
    fireEvent.change(screen.getByLabelText(/HuggingFace model/), { target: { value: 'org/model' } })
    fireEvent.change(screen.getByLabelText(/^API key$/), { target: { value: 'key-typed' } })
    fireEvent.click(screen.getByRole('button', { name: /Create service/ }))

    await waitFor(() => expect(screen.getByText('API key:')).toBeTruthy())
    const [, opts] = fetchAPIMock.mock.calls.find(([ep, o]) => ep === '/services' && o?.method === 'POST')
    const body = JSON.parse(opts.body)
    expect(body.model_name).toBe('org/model')
    expect(body.model_path).toBeUndefined()
    expect(body.api_key).toBe('key-typed')
  })

  it('shows server validation details on a 400', async () => {
    fetchAPIMock.mockImplementation(async (endpoint) => {
      if (endpoint === '/system/info') return { models: [] }
      if (endpoint.startsWith('/flag-metadata/')) return { optional_flags: {} }
      const e = new Error('Validation failed')
      e.details = ['Invalid reasoning level "LOW": levels must be lowercase', 'Unknown llamacpp flag: --bogus']
      throw e
    })
    setup()
    fillForm()
    fireEvent.change(screen.getByLabelText(/Reasoning levels/), { target: { value: 'off,LOW' } })
    fireEvent.click(screen.getByRole('button', { name: /Create service/ }))

    await waitFor(() => expect(screen.getByText('Validation failed')).toBeTruthy())
    expect(screen.getByText(/levels must be lowercase/)).toBeTruthy()
    expect(screen.getByText(/Unknown llamacpp flag: --bogus/)).toBeTruthy()
  })

  it('shows the created service, its key, and navigates on Open service', async () => {
    const onClose = vi.fn()
    mockApi({
      service_name: 'llamacpp-test-model',
      port: 3303,
      api_key: 'key-gen',
      warnings: ['Unknown llamacpp flag: --bogus (not in the engine\'s recorded flag surface; it will be passed through and may fail at startup)'],
      success: true,
    })
    setup({ onClose })
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: /Create service/ }))

    await waitFor(() => expect(screen.getByText('API key:')).toBeTruthy())
    expect(screen.getByText('llamacpp-test-model')).toBeTruthy()
    expect(screen.getByText('key-gen')).toBeTruthy()
    expect(screen.getByText(/not in the engine's recorded surface/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Open service/ }))
    expect(onClose).toHaveBeenCalled()
    expect(navigateMock).toHaveBeenCalledWith('/services/llamacpp-test-model')
  })
})
