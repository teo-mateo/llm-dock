import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import CreateServiceModal from './CreateServiceModal'
import { resetEngineCatalogue } from '../hooks/useEngineCatalogue'
import { ENGINES_RESPONSE } from '../test/engineCatalogue'

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
    if (endpoint === '/engines') return ENGINES_RESPONSE
    if (endpoint === '/system/info') return { models: [] }
    if (endpoint.startsWith('/flag-metadata/')) return { optional_flags: {} }
    if (endpoint === '/services' && opts?.method === 'POST') return result
    return {}
  })
}

async function setup(props = {}) {
  // Default stubs for the two read endpoints; a test that set an
  // implementation first (mockApi or custom) keeps it.
  if (!fetchAPIMock.getMockImplementation()) {
    fetchAPIMock.mockImplementation(async (endpoint) => {
      if (endpoint === '/engines') return ENGINES_RESPONSE
      if (endpoint === '/system/info') return { models: [] }
      if (endpoint.startsWith('/flag-metadata/')) return { optional_flags: {} }
      throw new Error('unexpected fetchAPI call: ' + endpoint)
    })
  }
  const view = render(
    <CreateServiceModal
      services={SERVICES}
      onClose={vi.fn()}
      onCreated={vi.fn()}
      {...props}
    />
  )
  await screen.findAllByRole('radio')
  return view
}

function fillForm({ alias = 'test-model', modelPath = '/hf-cache/m.gguf' } = {}) {
  fireEvent.change(screen.getByLabelText(/Service alias/), { target: { value: alias } })
  fireEvent.change(screen.getByLabelText(/Model path \(container\)/), { target: { value: modelPath } })
}

afterEach(() => {
  cleanup()
  resetEngineCatalogue()
  fetchAPIMock.mockReset()
  navigateMock.mockReset()
})

describe('CreateServiceModal', () => {
  it('closes on Escape', async () => {
    const onClose = vi.fn()
    await setup({ onClose })
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('offers one entry per GGUF model: first shard only, no mmproj', async () => {
    fetchAPIMock.mockImplementation(async (endpoint) => {
      if (endpoint === '/engines') return ENGINES_RESPONSE
      if (endpoint === '/system/info') {
        return {
          models: [
            {
              name: 'org/sharded',
              full_name: 'org/sharded [Q4_K]',
              files: [
                { name: 'Sharded-Q4_K-00001-of-00004.gguf', path: '/home/x/.cache/models/sharded/Sharded-Q4_K-00001-of-00004.gguf', size_str: '9.00 GB' },
                { name: 'Sharded-Q4_K-00002-of-00004.gguf', path: '/home/x/.cache/models/sharded/Sharded-Q4_K-00002-of-00004.gguf', size_str: '9.00 GB' },
                { name: 'Sharded-Q4_K-00003-of-00004.gguf', path: '/home/x/.cache/models/sharded/Sharded-Q4_K-00003-of-00004.gguf', size_str: '9.00 GB' },
                { name: 'Sharded-Q4_K-00004-of-00004.gguf', path: '/home/x/.cache/models/sharded/Sharded-Q4_K-00004-of-00004.gguf', size_str: '9.00 GB' },
                { name: 'mmproj-BF16.gguf', path: '/home/x/.cache/models/sharded/mmproj-BF16.gguf', size_str: '888 MB' },
              ],
            },
            {
              name: 'org/plain',
              files: [{ name: 'plain.gguf', path: '/home/x/.cache/models/plain/plain.gguf', size_str: '5.5 GB' }],
            },
          ],
        }
      }
      if (endpoint.startsWith('/flag-metadata/')) return { optional_flags: {} }
      throw new Error('unexpected fetchAPI call: ' + endpoint)
    })
    await setup()
    await waitFor(() => expect(screen.getAllByRole('option').length).toBeGreaterThan(1))
    const options = screen.getAllByRole('option').map(o => o.textContent)
    expect(options).toContain('org/sharded [Q4_K] — Sharded-Q4_K — 4 shards')
    expect(options).toContain('org/plain — plain.gguf — 5.5 GB')
    expect(options.some(t => /mmproj/i.test(t))).toBe(false)
    expect(options.some(t => /0000[2-4]/.test(t))).toBe(false)
  })
  it('defaults to llama.cpp with the next free port from the service list', async () => {
    await setup()
    expect(screen.getByRole('radio', { name: /^llama\.cpp/ }).checked).toBe(true)
    expect(screen.getByLabelText(/Port/).value).toBe('3303')
    expect(screen.getByLabelText(/Model path \(container\)/)).toBeTruthy()
  })

  it('switches the model field to a HuggingFace name for vLLM', async () => {
    await setup()
    fireEvent.click(screen.getByRole('radio', { name: /vLLM/ }))
    expect(screen.queryByLabelText(/Model path \(container\)/)).toBeNull()
    expect(screen.getByLabelText(/HuggingFace model/)).toBeTruthy()
  })

  it('creates a Pennyroyal service with a directory path and sglang prefix', async () => {
    mockApi({ service_name: 'sglang-next', port: 3303, api_key: 'key', success: true })
    await setup()
    fireEvent.click(screen.getByRole('radio', { name: /SGLang/ }))
    expect(screen.queryByRole('combobox', { name: /Pick a discovered file/ })).toBeNull()
    fireEvent.change(screen.getByLabelText(/Model path \(container\)/), { target: { value: '/local-models/next' } })
    fireEvent.change(screen.getByLabelText(/Service alias/), { target: { value: 'next' } })
    fireEvent.click(screen.getByRole('button', { name: /Create service/ }))
    await waitFor(() => expect(fetchAPIMock).toHaveBeenCalledWith('/services', expect.objectContaining({ method: 'POST' })))
    const [, options] = fetchAPIMock.mock.calls.find(([url, opts]) => url === '/services' && opts?.method === 'POST')
    expect(JSON.parse(options.body)).toMatchObject({ template_type: 'sglang', model_path: '/local-models/next', alias: 'next' })
  })

  it('previews the generated service name from the alias', async () => {
    await setup()
    fireEvent.change(screen.getByLabelText(/Service alias/), { target: { value: 'Foo Bar' } })
    expect(screen.getByText('llamacpp-foo-bar')).toBeTruthy()
  })

  it('switches the name preview with the engine prefix', async () => {
    await setup()
    fireEvent.change(screen.getByLabelText(/Service alias/), { target: { value: 'test' } })
    fireEvent.click(screen.getByRole('radio', { name: /TabbyAPI/ }))
    expect(screen.getByText('exl3-test')).toBeTruthy()
  })

  it('disables the create button while required fields are empty', async () => {
    await setup()
    expect(screen.getByRole('button', { name: /Create service/ }).disabled).toBe(true)
  })

  it('posts the payload for a file-based engine and omits an empty api key', async () => {
    mockApi({ service_name: 'llamacpp-test-model', port: 3303, api_key: 'key-gen', success: true })
    const onCreated = vi.fn()
    await setup({ onCreated })
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
    await setup()
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
      if (endpoint === '/engines') return ENGINES_RESPONSE
      if (endpoint === '/system/info') return { models: [] }
      if (endpoint.startsWith('/flag-metadata/')) return { optional_flags: {} }
      const e = new Error('Validation failed')
      e.details = ['Invalid reasoning level "LOW": levels must be lowercase', 'Unknown llamacpp flag: --bogus']
      throw e
    })
    await setup()
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
    await setup({ onClose })
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

  describe('engine catalogue states', () => {
    function mockEngines(engines) {
      fetchAPIMock.mockImplementation(async (endpoint) => {
        if (endpoint === '/engines') return engines instanceof Error ? Promise.reject(engines) : engines
        if (endpoint === '/system/info') return { models: [] }
        if (endpoint.startsWith('/flag-metadata/')) return { optional_flags: {} }
        throw new Error('unexpected fetchAPI call: ' + endpoint)
      })
    }

    function renderModal() {
      return render(<CreateServiceModal services={SERVICES} onClose={vi.fn()} onCreated={vi.fn()} />)
    }

    it('says it is loading and offers no engine until the catalogue arrives', async () => {
      let release
      fetchAPIMock.mockImplementation((endpoint) => {
        if (endpoint === '/engines') return new Promise(resolve => { release = () => resolve(ENGINES_RESPONSE) })
        if (endpoint === '/system/info') return Promise.resolve({ models: [] })
        return Promise.resolve({ optional_flags: {} })
      })

      renderModal()

      expect(screen.getByRole('status').textContent).toMatch(/Loading engines/)
      expect(screen.queryAllByRole('radio')).toHaveLength(0)
      expect(screen.getByRole('button', { name: /Create service/ })).toBeDisabled()
      release()
      expect((await screen.findAllByRole('radio')).length).toBeGreaterThan(0)
      expect(screen.queryByRole('status')).toBeNull()
    })

    it('shows why the list is empty when the request fails, and recovers on Retry', async () => {
      mockEngines(new Error('HTTP 502'))
      renderModal()

      const alert = await screen.findByRole('alert')
      expect(alert.textContent).toMatch(/Couldn't load the engine list: HTTP 502/)
      expect(screen.queryAllByRole('radio')).toHaveLength(0)
      expect(screen.getByRole('button', { name: /Create service/ })).toBeDisabled()

      mockEngines(ENGINES_RESPONSE)
      fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

      expect((await screen.findAllByRole('radio')).length).toBeGreaterThan(0)
      expect(screen.queryByRole('alert')).toBeNull()
    })

    it('says so when the server reports no engines', async () => {
      mockEngines({ engines: [] })
      renderModal()

      expect((await screen.findByRole('alert')).textContent).toMatch(/server reported no engines/)
      expect(screen.getByRole('button', { name: /Create service/ })).toBeDisabled()
    })

    it('offers an engine the server added, with no code change, and posts its type and path', async () => {
      const added = {
        type: 'future_engine', label: 'Future', hint: 'a future file', model_source: 'file',
        placeholder: '/future/…', gguf_picker: false, chat: true, metrics: false, benchmark: false,
        name_prefix: 'fut',
      }
      fetchAPIMock.mockImplementation(async (endpoint, opts) => {
        if (endpoint === '/engines') return { engines: [added] }
        if (endpoint === '/system/info') return { models: [] }
        if (endpoint.startsWith('/flag-metadata/')) return { optional_flags: {} }
        if (endpoint === '/services' && opts?.method === 'POST') return { service_name: 'fut-x', api_key: 'k' }
        throw new Error('unexpected fetchAPI call: ' + endpoint)
      })
      renderModal()
      await screen.findByRole('radio', { name: /Future/ })

      fireEvent.change(screen.getByLabelText(/Service alias/), { target: { value: 'x' } })
      fireEvent.change(screen.getByLabelText(/Model path \(container\)/), { target: { value: '/future/model' } })
      expect(screen.getByLabelText(/Model path \(container\)/).placeholder).toBe('/future/…')
      expect(screen.getByText('fut-x')).toBeTruthy()
      fireEvent.click(screen.getByRole('button', { name: /Create service/ }))

      await waitFor(() => {
        const post = fetchAPIMock.mock.calls.find(c => c[0] === '/services')
        expect(JSON.parse(post[1].body)).toMatchObject({ template_type: 'future_engine', model_path: '/future/model' })
      })
    })
  })
})
