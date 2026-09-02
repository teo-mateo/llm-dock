import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'

const mockSave = vi.fn()
const mockReset = vi.fn()
const mockRefreshCatalog = vi.fn()
const mockProviderRetry = vi.fn()

let settingsState
let catalogState
let providerState
let requestedProviderIds

vi.mock('../../hooks/useOpenRouterModels', () => ({
  default: () => settingsState,
}))

vi.mock('../../hooks/useOpenRouterCatalog', () => ({
  default: () => catalogState,
}))

vi.mock('../../hooks/useModelProviders', () => ({
  default: (ids) => {
    requestedProviderIds = ids
    return providerState
  },
}))

import OpenRouterModelsPicker from './OpenRouterModelsPicker'
import { MAX_PROVIDER_BATCH } from '../../services/openrouterProviders'

// jsdom has no IntersectionObserver, and the picker treats its absence as "no
// provider lines" rather than an error. Tests that care about which rows are
// wanted install this stub, which records what the pane observes and lets the
// test decide what is on screen.
class ObserverStub {
  static instances = []

  constructor(callback) {
    this.callback = callback
    this.targets = []
    ObserverStub.instances.push(this)
  }

  observe(el) {
    this.targets.push(el)
  }

  unobserve(el) {
    this.targets = this.targets.filter((t) => t !== el)
  }

  disconnect() {
    this.targets = []
  }

  report(...ids) {
    this.callback(
      ids.map((id) => ({ isIntersecting: true, target: { dataset: { modelId: id } } })),
      this,
    )
  }
}

const entry = (id, name, extra = {}) => ({
  id,
  name,
  label: name.includes(': ') ? name.split(': ')[1] : name,
  created: 1700000000,
  context_length: 131072,
  price_in: 1,
  price_out: 3,
  price_cache_read: null,
  free: false,
  variant: null,
  vendor: id.split('/')[0],
  router: id.startsWith('openrouter/'),
  image_out: false,
  audio_out: false,
  chat_model: !id.startsWith('openrouter/') && !id.includes('image') && !id.includes('audio'),
  tools: true,
  structured_outputs: true,
  reasoning: false,
  input_modalities: ['text'],
  tokenizer: null,
  hugging_face_id: null,
  expires: null,
  deprecated: false,
  benchmarks: null,
  ...extra,
})

const CATALOG = [
  entry('z-ai/glm-5.2', 'Z.ai: GLM 5.2'),
  entry('z-ai/glm-5.2:free', 'Z.ai: GLM 5.2 (free)', { free: true, price_in: 0, price_out: 0, variant: 'free' }),
  entry('anthropic/claude-opus-5', 'Anthropic: Claude Opus 5', { price_in: 5, benchmarks: { intelligence: 90, coding: 90, agentic: 90 } }),
  entry('google/gemini-3-pro-image', 'Google: Gemini 3 Pro Image', { image_out: true, chat_model: false, input_modalities: ['text', 'image'] }),
  entry('openrouter/auto', 'Auto Router', { router: true, chat_model: false }),
  entry('mistralai/mistral-tiny', 'Mistral: Mistral Tiny', { tools: false }),
]

const CURRENT = [
  { id: 'z-ai/glm-5.2', label: 'GLM 5.2' },
  { id: 'anthropic/claude-opus-5', label: 'Claude Opus 5' },
  { id: 'vendor/retired-model', label: 'Retired Model' },
]

const PROVIDER_DETAIL = {
  'z-ai/glm-5.2': [
    { provider: 'Z.ai', quantization: 'fp8', context_length: 200000, max_completion_tokens: null, price_in: 1, price_out: 3, uptime_1d: 99.9, status: 0, tools: true },
    { provider: 'DeepInfra', quantization: 'int4', context_length: 131072, max_completion_tokens: 8192, price_in: 1.2, price_out: 3.6, uptime_1d: 98.4, status: -2, tools: true },
    { provider: 'Novita', quantization: 'unknown', context_length: 200000, max_completion_tokens: null, price_in: 2.5, price_out: 4, uptime_1d: 99.1, status: 0, tools: false },
    { provider: 'AtlasCloud', quantization: 'fp8', context_length: 200000, max_completion_tokens: null, price_in: 3, price_out: 5, uptime_1d: 100, status: 0, tools: true },
  ],
  'anthropic/claude-opus-5': [
    { provider: 'Anthropic', quantization: 'bf16', context_length: 200000, max_completion_tokens: null, price_in: 5, price_out: 25, uptime_1d: 99.99, status: 0, tools: true },
  ],
  'z-ai/glm-5.2:free': [],
}

beforeEach(() => {
  mockSave.mockReset().mockImplementation(async (models) => ({ ...settingsState.data, current: models, customized: true }))
  mockReset.mockReset().mockImplementation(async () => ({ ...settingsState.data, current: CURRENT, customized: false }))
  mockRefreshCatalog.mockReset()
  settingsState = {
    data: { configured: true, current: CURRENT, builtin: CURRENT, customized: false },
    loading: false,
    error: null,
    save: mockSave,
    reset: mockReset,
    refresh: vi.fn(),
  }
  catalogState = {
    data: {
      models: CATALOG,
      count: CATALOG.length,
      fetched_at: '2026-08-31T00:00:00Z',
      stale: false,
      cached: true,
      error: null,
      configured: true,
      known_ids: CATALOG.map((m) => m.id),
    },
    loading: false,
    error: null,
    refresh: mockRefreshCatalog,
  }
  providerState = { byId: PROVIDER_DETAIL, loading: false, error: null, retry: mockProviderRetry }
  requestedProviderIds = []
  ObserverStub.instances = []
  delete window.IntersectionObserver
})

afterEach(() => {
  cleanup()
  delete window.IntersectionObserver
})

const dropdown = () => screen.getByText(/Chat dropdown/).textContent

describe('OpenRouterModelsPicker', () => {
  it('renders the curated list and the catalog', () => {
    render(<OpenRouterModelsPicker />)
    expect(screen.getByDisplayValue('GLM 5.2')).toBeInTheDocument()
    expect(dropdown()).toContain('3')
    expect(screen.getByText(/showing 3 of 6/)).toBeInTheDocument()
  })

  it('adds a catalog model with the label derived from the catalog', () => {
    render(<OpenRouterModelsPicker />)
    fireEvent.click(screen.getByLabelText('Add Z.ai: GLM 5.2 (free) to dropdown'))
    expect(screen.getByDisplayValue('GLM 5.2 (free)')).toBeInTheDocument()
    expect(dropdown()).toContain('4')
    expect(screen.getByText('Unsaved')).toBeInTheDocument()
  })

  it('toggles an already-added model off from the same control', () => {
    render(<OpenRouterModelsPicker />)
    fireEvent.click(screen.getByLabelText('Remove Z.ai: GLM 5.2 from dropdown'))
    expect(dropdown()).toContain('2')
    expect(screen.getByLabelText('Add Z.ai: GLM 5.2 to dropdown')).toBeInTheDocument()
  })

  it('saves the short list in the visible order', async () => {
    render(<OpenRouterModelsPicker />)
    fireEvent.click(screen.getAllByLabelText('Move down')[0])
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(mockSave).toHaveBeenCalled())
    expect(mockSave.mock.calls[0][0].map((m) => m.id)).toEqual([
      'anthropic/claude-opus-5',
      'z-ai/glm-5.2',
      'vendor/retired-model',
    ])
  })

  it('keeps an edited label through the save payload', async () => {
    render(<OpenRouterModelsPicker />)
    fireEvent.change(screen.getByLabelText('Label for z-ai/glm-5.2'), { target: { value: 'GLM' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(mockSave).toHaveBeenCalled())
    expect(mockSave.mock.calls[0][0][0]).toEqual({ id: 'z-ai/glm-5.2', label: 'GLM' })
  })

  it('badges a curated id the catalog no longer offers', () => {
    render(<OpenRouterModelsPicker />)
    expect(screen.getByText('not in catalog')).toBeInTheDocument()
  })

  it('filters the catalog by search text', async () => {
    render(<OpenRouterModelsPicker />)
    fireEvent.change(screen.getByLabelText('Search models'), { target: { value: 'opus' } })
    await waitFor(() => expect(screen.getByText(/showing 1 of 6/)).toBeInTheDocument())
    expect(screen.queryByText('Z.ai: GLM 5.2')).not.toBeInTheDocument()
  })

  it('adds the first unadded match on Enter', async () => {
    render(<OpenRouterModelsPicker />)
    fireEvent.change(screen.getByLabelText('Search models'), { target: { value: 'glm' } })
    await waitFor(() => expect(screen.getByText(/showing 2 of 6/)).toBeInTheDocument())
    fireEvent.keyDown(screen.getByLabelText('Search models'), { key: 'Enter' })
    expect(dropdown()).toContain('4')
    expect(screen.getByDisplayValue('GLM 5.2 (free)')).toBeInTheDocument()
  })

  it('filters by vendor', () => {
    render(<OpenRouterModelsPicker />)
    fireEvent.click(screen.getByRole('button', { name: 'Filters' }))
    fireEvent.click(screen.getByLabelText(/^anthropic/))
    expect(screen.getByText(/showing 1 of 6/)).toBeInTheDocument()
  })

  it('hides tool-incapable models while the tools filter is on', () => {
    render(<OpenRouterModelsPicker />)
    expect(screen.queryByText('Mistral: Mistral Tiny')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Filters' }))
    fireEvent.click(screen.getByLabelText('tool-capable'))
    expect(screen.getByText('Mistral: Mistral Tiny')).toBeInTheDocument()
  })

  it('hides non-chat rows by default and reveals them behind a counted toggle', () => {
    render(<OpenRouterModelsPicker />)
    expect(screen.queryByText('Auto Router')).not.toBeInTheDocument()
    expect(screen.queryByText('Google: Gemini 3 Pro Image')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Filters' }))
    fireEvent.click(screen.getByLabelText(/show 2 non-chat/))
    expect(screen.getByText('Auto Router')).toBeInTheDocument()
    expect(screen.getByText('Google: Gemini 3 Pro Image')).toBeInTheDocument()
  })

  it('hides :batch variants by default', () => {
    const batch = entry('z-ai/glm-5.2:batch', 'Z.ai: GLM 5.2 (batch)', { variant: 'batch' })
    catalogState.data = { ...catalogState.data, models: [...CATALOG, batch] }
    render(<OpenRouterModelsPicker />)
    expect(screen.queryByText('Z.ai: GLM 5.2 (batch)')).not.toBeInTheDocument()
    expect(screen.getByText(/showing 3 of 7/)).toBeInTheDocument()
  })

  it('reads as filtered, not broken, when nothing matches', async () => {
    render(<OpenRouterModelsPicker />)
    fireEvent.change(screen.getByLabelText('Search models'), { target: { value: 'zzzz' } })
    await waitFor(() => expect(screen.getByText(/No models match/)).toBeInTheDocument())
  })

  it('discards local edits', () => {
    render(<OpenRouterModelsPicker />)
    fireEvent.click(screen.getByLabelText('Add Z.ai: GLM 5.2 (free) to dropdown'))
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }))
    expect(dropdown()).toContain('3')
    expect(screen.queryByText('Unsaved')).not.toBeInTheDocument()
    expect(mockSave).not.toHaveBeenCalled()
  })

  it('resets to the built-in list through the two-step confirm', async () => {
    settingsState.data = { ...settingsState.data, customized: true }
    render(<OpenRouterModelsPicker />)
    fireEvent.click(screen.getByRole('button', { name: 'Reset to built-in' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm reset' }))
    await waitFor(() => expect(mockReset).toHaveBeenCalled())
  })

  it('refreshes the catalog through the header button', () => {
    render(<OpenRouterModelsPicker />)
    fireEvent.click(screen.getByRole('button', { name: /Refresh/ }))
    expect(mockRefreshCatalog).toHaveBeenCalledWith(true)
  })

  it('offers a retry without blocking the short list when the catalog fails', () => {
    catalogState = { ...catalogState, data: null, error: 'HTTP 502' }
    render(<OpenRouterModelsPicker />)
    expect(screen.getByText(/Couldn't reach the OpenRouter catalog/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(mockRefreshCatalog).toHaveBeenCalledWith(true)
    expect(screen.getByDisplayValue('GLM 5.2')).toBeInTheDocument()
  })

  it('warns without an API key', () => {
    settingsState.data = { ...settingsState.data, configured: false }
    render(<OpenRouterModelsPicker />)
    expect(screen.getByText(/OPENROUTER_API_KEY/)).toBeInTheDocument()
  })

  it('lets the list be emptied and saved as empty', async () => {
    render(<OpenRouterModelsPicker />)
    const removes = () => screen.getAllByLabelText(/^Remove (z-ai|anthropic|vendor)/)
    removes().forEach((btn) => fireEvent.click(btn))
    expect(dropdown()).toContain('0')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith([]))
  })

  it('gates Save while the shared JSON panel is invalid, and syncs it when valid', async () => {
    render(<OpenRouterModelsPicker />)
    fireEvent.click(screen.getByLabelText('Add Z.ai: GLM 5.2 (free) to dropdown'))
    fireEvent.click(screen.getByRole('button', { name: /Advanced: edit JSON/ }))
    const area = screen.getByLabelText('Curated models as JSON')
    fireEvent.change(area, { target: { value: '[{"id": ' } })
    expect(screen.getByText(/Invalid JSON/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    fireEvent.change(area, { target: { value: '[{"id": "new/vendor", "label": "New"}]' } })
    expect(screen.getByDisplayValue('New')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith([{ id: 'new/vendor', label: 'New' }]))
  })

  it('sorts by price ascending by default', () => {
    render(<OpenRouterModelsPicker />)
    const order = screen
      .getAllByRole('button', { name: /^(Add|Remove) / })
      .map((b) => b.getAttribute('aria-label'))
    expect(order[0]).toContain('Z.ai: GLM 5.2 (free)')
  })

  it('re-sorts when the sort changes', () => {
    render(<OpenRouterModelsPicker />)
    fireEvent.change(screen.getByLabelText('Sort models'), { target: { value: 'name' } })
    const order = screen
      .getAllByRole('button', { name: /^(Add|Remove) / })
      .map((b) => b.getAttribute('aria-label'))
    expect(order[0]).toContain('Anthropic: Claude Opus 5')
  })

  describe('provider detail', () => {
    it('shows provider count, names, quantizations and price spread', () => {
      render(<OpenRouterModelsPicker />)
      expect(screen.getByText('4 providers')).toBeInTheDocument()
      expect(screen.getByText('Z.ai, DeepInfra, Novita +1')).toBeInTheDocument()
      expect(screen.getByText('· fp8/int4')).toBeInTheDocument()
      expect(screen.getByText('· $1.00/M–$3.00/M')).toBeInTheDocument()
    })

    it('expands into a per-provider table', () => {
      render(<OpenRouterModelsPicker />)
      fireEvent.click(screen.getByText('4 providers'))
      expect(screen.getByText('no tools')).toBeInTheDocument()
      expect(screen.getByText('status -2')).toBeInTheDocument()
      expect(screen.getByText('98.4%')).toBeInTheDocument()
      expect(screen.queryByText('8192')).not.toBeInTheDocument()   // max tokens not shown
    })

    it('uses singular wording for a single-provider model', () => {
      render(<OpenRouterModelsPicker />)
      expect(screen.getByText('provider')).toBeInTheDocument()
      expect(screen.getByText('Anthropic')).toBeInTheDocument()
    })

    it('says so when upstream lists no endpoints', () => {
      render(<OpenRouterModelsPicker />)
      expect(screen.getByText('no endpoints listed upstream')).toBeInTheDocument()
    })

    it('shows no provider line for rows whose detail has not landed', () => {
      providerState = { byId: {}, loading: false, error: null, retry: mockProviderRetry }
      render(<OpenRouterModelsPicker />)
      expect(screen.queryByText(/provider/i)).not.toBeInTheDocument()
    })

    it('offers a retry when the provider batch failed', () => {
      providerState = { ...providerState, error: 'HTTP 502' }
      render(<OpenRouterModelsPicker />)
      fireEvent.click(screen.getByText('providers unavailable — retry'))
      expect(mockProviderRetry).toHaveBeenCalled()
    })

    it('reports loading without hiding the rows', () => {
      providerState = { ...providerState, loading: true }
      render(<OpenRouterModelsPicker />)
      expect(screen.getByText(/loading providers/i)).toBeInTheDocument()
      expect(screen.getByText('Z.ai: GLM 5.2')).toBeInTheDocument()
    })

    it('keeps two endpoints from one provider as distinct rows', () => {
      // Real data: one provider routinely lists several endpoints for a model at
      // the same (absent, so "unknown") quantization.
      providerState = {
        ...providerState,
        byId: {
          'z-ai/glm-5.2': [
            { provider: 'Azure', quantization: 'unknown', context_length: 400000, max_completion_tokens: null, price_in: 5, price_out: 25, uptime_1d: 99.9, status: 0, tools: true },
            { provider: 'Azure', quantization: 'unknown', context_length: 1000000, max_completion_tokens: null, price_in: 6, price_out: 30, uptime_1d: 99.5, status: 0, tools: true },
          ],
        },
      }
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      render(<OpenRouterModelsPicker />)
      fireEvent.click(screen.getByText('2 providers'))
      expect(screen.getAllByText('Azure')).toHaveLength(2)
      expect(spy.mock.calls.flat().join(' ')).not.toContain('same key')
      spy.mockRestore()
    })

    it('asks for no provider detail while nothing is reported in view', () => {
      render(<OpenRouterModelsPicker />)
      expect(requestedProviderIds).toEqual([])
    })

    it('registers the rendered rows with the observer', () => {
      window.IntersectionObserver = ObserverStub
      render(<OpenRouterModelsPicker />)
      const observed = ObserverStub.instances.at(-1).targets.map((el) => el.dataset.modelId)
      expect(observed).toEqual(expect.arrayContaining(['z-ai/glm-5.2', 'anthropic/claude-opus-5']))
      expect(observed).not.toContain('mistralai/mistral-tiny')     // filtered out, so not mounted
    })

    it('asks for the rows the observer reports rather than the head of the list', async () => {
      window.IntersectionObserver = ObserverStub
      render(<OpenRouterModelsPicker />)
      ObserverStub.instances.at(-1).report('anthropic/claude-opus-5')
      await waitFor(() => expect(requestedProviderIds).toEqual(['anthropic/claude-opus-5']))
    })

    it('caps the wanted set at the server batch limit', async () => {
      const many = Array.from({ length: MAX_PROVIDER_BATCH + 20 }, (_, i) =>
        entry(`vendor/model-${i}`, `Vendor: Model ${i}`),
      )
      catalogState.data = {
        ...catalogState.data,
        models: many,
        count: many.length,
        known_ids: many.map((m) => m.id),
      }
      window.IntersectionObserver = ObserverStub
      render(<OpenRouterModelsPicker />)
      ObserverStub.instances.at(-1).report(...many.map((m) => m.id))
      await waitFor(() => expect(requestedProviderIds.length).toBe(MAX_PROVIDER_BATCH))
    })
  })
})
