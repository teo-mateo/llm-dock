import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'

const mockSave = vi.fn()
const mockRemove = vi.fn()
const mockTest = vi.fn()
let hookState

vi.mock('../../hooks/useProviderSettings', () => ({ default: () => hookState }))

import ProvidersSettings from './ProvidersSettings'

const PRESET = { id: 'mistral', name: 'Mistral', base_url: 'https://api.mistral.ai/v1', api_key_env: 'MISTRAL_API_KEY' }

beforeEach(() => {
  for (const m of [mockSave, mockRemove, mockTest]) m.mockReset()
  mockSave.mockResolvedValue({})
  hookState = { data: { providers: [], presets: [PRESET] }, error: null, save: mockSave, remove: mockRemove, test: mockTest }
})
afterEach(cleanup)

describe('ProvidersSettings', () => {
  it('adds a preset with a pasted key', async () => {
    render(<ProvidersSettings />)
    fireEvent.click(screen.getByText('Add Mistral'))
    fireEvent.change(screen.getByPlaceholderText('paste key'), { target: { value: ' sk-abc ' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith('mistral', {
      name: 'Mistral', base_url: 'https://api.mistral.ai/v1', api_key_env: 'MISTRAL_API_KEY', api_key: 'sk-abc',
    }))
  })

  it('editing without a new key leaves the stored key alone', async () => {
    hookState.data.providers = [{ ...PRESET, enabled: true, key_source: 'stored' }]
    render(<ProvidersSettings />)
    expect(screen.getByText('key stored')).toBeTruthy()
    fireEvent.click(screen.getByText('Edit'))
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(mockSave).toHaveBeenCalled())
    expect(mockSave.mock.calls[0][1]).not.toHaveProperty('api_key')
  })

  it('warns when the env var is not visible to the dashboard', () => {
    hookState.data.providers = [{ ...PRESET, enabled: true, key_source: null }]
    render(<ProvidersSettings />)
    expect(screen.getByText(/MISTRAL_API_KEY is not set for the dashboard/)).toBeTruthy()
  })

  it('reports a test result', async () => {
    hookState.data.providers = [{ ...PRESET, enabled: true, key_source: 'stored' }]
    mockTest.mockResolvedValue({ ok: true, model_count: 14, error: null })
    render(<ProvidersSettings />)
    fireEvent.click(screen.getByText('Test'))
    await waitFor(() => expect(screen.getByText('Connected — 14 chat models')).toBeTruthy())
  })
})
