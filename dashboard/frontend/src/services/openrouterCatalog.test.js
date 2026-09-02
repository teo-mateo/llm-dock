import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getOpenRouterCatalog } from './openrouterCatalog'

vi.mock('../api', () => ({
  fetchAPI: vi.fn(() => Promise.resolve({ models: [] })),
}))

import { fetchAPI } from '../api'

beforeEach(() => fetchAPI.mockClear())

describe('getOpenRouterCatalog', () => {
  it('hits the plain path by default', () => {
    getOpenRouterCatalog()
    expect(fetchAPI).toHaveBeenCalledWith('/chat/settings/openrouter-catalog')
  })

  it('busts the server cache when refreshing', () => {
    getOpenRouterCatalog({ refresh: true })
    expect(fetchAPI).toHaveBeenCalledWith('/chat/settings/openrouter-catalog?refresh=1')
  })

  it('requests descriptions only when asked', () => {
    getOpenRouterCatalog({ detail: true })
    expect(fetchAPI).toHaveBeenCalledWith('/chat/settings/openrouter-catalog?detail=1')
  })

  it('combines both flags', () => {
    getOpenRouterCatalog({ refresh: true, detail: true })
    expect(fetchAPI).toHaveBeenCalledWith('/chat/settings/openrouter-catalog?refresh=1&detail=1')
  })
})
