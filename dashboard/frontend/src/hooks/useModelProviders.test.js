import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import useModelProviders from './useModelProviders'

const getProviderSummaries = vi.fn()

vi.mock('../services/openrouterProviders', () => ({
  MAX_PROVIDER_BATCH: 60,
  getProviderSummaries: (...args) => getProviderSummaries(...args),
}))

const payload = (models, extra = {}) => ({ models, missing: [], stale: [], ...extra })

beforeEach(() => {
  getProviderSummaries.mockReset()
  getProviderSummaries.mockResolvedValue(payload({}))
})

afterEach(() => vi.restoreAllMocks())

describe('useModelProviders', () => {
  it('fetches the ids it is given', async () => {
    getProviderSummaries.mockResolvedValue(payload({ 'a/b': [{ provider: 'DeepInfra', price_in: 1 }] }))
    const { result } = renderHook(() => useModelProviders(['a/b']))
    await waitFor(() => expect(result.current.byId['a/b']).toBeDefined())
    expect(getProviderSummaries).toHaveBeenCalledTimes(1)
    expect(getProviderSummaries.mock.calls[0][0]).toEqual(['a/b'])
  })

  it('never asks for the same id twice while mounted', async () => {
    getProviderSummaries.mockResolvedValue(payload({ 'a/b': [{ provider: 'X', price_in: 1 }] }))
    const { rerender, result } = renderHook(({ ids }) => useModelProviders(ids), {
      initialProps: { ids: ['a/b'] },
    })
    await waitFor(() => expect(result.current.byId['a/b']).toBeDefined())
    rerender({ ids: ['a/b', 'c/d'] })
    await waitFor(() => expect(getProviderSummaries).toHaveBeenCalledTimes(2))
    rerender({ ids: ['a/b', 'c/d'] })
    await waitFor(() => expect(getProviderSummaries).toHaveBeenCalledTimes(2))
    expect(getProviderSummaries.mock.calls[1][0]).toEqual(['c/d'])
  })

  it('caps the batch instead of chunking it', async () => {
    const ids = Array.from({ length: 75 }, (_, i) => `vendor/m${i}`)
    await act(async () => { renderHook(() => useModelProviders(ids)) })
    expect(getProviderSummaries.mock.calls[0][0]).toHaveLength(60)
  })

  it('re-requests ids the server reported as missing', async () => {
    getProviderSummaries
      .mockResolvedValueOnce(payload({}, { missing: ['a/b'] }))
      .mockResolvedValueOnce(payload({ 'a/b': [{ provider: 'X', price_in: 1 }] }))
    const { rerender, result } = renderHook(({ ids }) => useModelProviders(ids), {
      initialProps: { ids: ['a/b'] },
    })
    await waitFor(() => expect(result.current.byId['a/b']).toBeUndefined())
    rerender({ ids: ['a/b', 'z/z'] })
    await waitFor(() => expect(result.current.byId['a/b']).toBeDefined())
  })

  it('surfaces a failed batch and retries it', async () => {
    getProviderSummaries
      .mockRejectedValueOnce(new Error('HTTP 502'))
      .mockResolvedValueOnce(payload({ 'a/b': [{ provider: 'X', price_in: 1 }] }))
    const { result } = renderHook(() => useModelProviders(['a/b']))
    await waitFor(() => expect(result.current.error).toBe('HTTP 502'))
    act(() => result.current.retry())
    await waitFor(() => expect(result.current.byId['a/b']).toBeDefined())
    expect(result.current.error).toBeNull()
    expect(getProviderSummaries).toHaveBeenCalledTimes(2)
  })

  it('keeps an id containing a comma in one piece', async () => {
    // The wanted set is keyed by a serialized string; a joined key would split
    // this into two ids that no such model will ever answer to.
    getProviderSummaries.mockResolvedValue(payload({ 'vendor/a,b': [{ provider: 'X', price_in: 1 }] }))
    const { result } = renderHook(() => useModelProviders(['vendor/a,b']))
    await waitFor(() => expect(result.current.byId['vendor/a,b']).toBeDefined())
    expect(getProviderSummaries.mock.calls[0][0]).toEqual(['vendor/a,b'])
  })

  it('does nothing for an empty id list', async () => {
    const { result } = renderHook(() => useModelProviders([]))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(getProviderSummaries).not.toHaveBeenCalled()
  })
})
