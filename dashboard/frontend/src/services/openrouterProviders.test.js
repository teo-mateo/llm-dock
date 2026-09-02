import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MAX_PROVIDER_BATCH, getProviderSummaries } from './openrouterProviders'

vi.mock('../api', () => ({
  fetchAPI: vi.fn(() => Promise.resolve({ models: {} })),
}))

import { fetchAPI } from '../api'

beforeEach(() => fetchAPI.mockClear())

describe('getProviderSummaries', () => {
  it('posts the batch to the provider endpoint', () => {
    getProviderSummaries(['a/b', 'c/d'])
    expect(fetchAPI).toHaveBeenCalledWith('/chat/settings/openrouter-catalog/endpoints', {
      method: 'POST',
      body: JSON.stringify({ ids: ['a/b', 'c/d'] }),
    })
  })

  it('omits the force flag unless asked', () => {
    getProviderSummaries(['a/b'], { force: true })
    expect(JSON.parse(fetchAPI.mock.calls[0][1].body)).toEqual({ ids: ['a/b'], force: true })
  })

  it('exposes the server batch cap so callers can slice to it', () => {
    expect(MAX_PROVIDER_BATCH).toBe(60)
  })
})
