import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'

const mockSave = vi.fn()
const mockReset = vi.fn()
const mockRefreshCatalog = vi.fn()

let settingsState
let catalogState

vi.mock('../../hooks/useOpenRouterModels', () => ({
  default: () => settingsState,
}))

vi.mock('../../hooks/useOpenRouterCatalog', () => ({
  default: () => catalogState,
}))

import OpenRouterModelsPicker from './OpenRouterModelsPicker'

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
})

afterEach(() => cleanup())

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
})
