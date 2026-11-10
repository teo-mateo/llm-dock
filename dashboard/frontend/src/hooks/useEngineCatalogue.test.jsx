import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import useEngineCatalogue, { resetEngineCatalogue } from './useEngineCatalogue'
import { ENGINES_RESPONSE, SAMPLE_ENGINES } from '../test/engineCatalogue'

const { fetchAPIMock } = vi.hoisted(() => ({ fetchAPIMock: vi.fn() }))
vi.mock('../api', () => ({ fetchAPI: (...a) => fetchAPIMock(...a) }))

beforeEach(() => {
  resetEngineCatalogue()
  fetchAPIMock.mockReset()
})

describe('useEngineCatalogue', () => {
  it('starts loading, then serves the engines and an index by type', async () => {
    fetchAPIMock.mockResolvedValue(ENGINES_RESPONSE)

    const { result } = renderHook(() => useEngineCatalogue())

    expect(result.current.status).toBe('loading')
    expect(result.current.engines).toEqual([])
    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(result.current.engines).toEqual(SAMPLE_ENGINES)
    expect(result.current.byType.vllm.model_source).toBe('repo')
    expect(fetchAPIMock).toHaveBeenCalledWith('/engines')
  })

  it('reports a failure with its message and recovers on retry', async () => {
    fetchAPIMock.mockRejectedValueOnce(new Error('HTTP 502')).mockResolvedValue(ENGINES_RESPONSE)

    const { result } = renderHook(() => useEngineCatalogue())

    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toBe('HTTP 502')
    expect(result.current.engines).toEqual([])

    act(() => result.current.retry())

    expect(result.current.status).toBe('loading')
    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(fetchAPIMock).toHaveBeenCalledTimes(2)
  })

  it('shares one request between callers that mount together', async () => {
    fetchAPIMock.mockResolvedValue(ENGINES_RESPONSE)

    const first = renderHook(() => useEngineCatalogue())
    const second = renderHook(() => useEngineCatalogue())

    await waitFor(() => expect(first.result.current.status).toBe('ready'))
    await waitFor(() => expect(second.result.current.status).toBe('ready'))
    expect(fetchAPIMock).toHaveBeenCalledTimes(1)
  })

  it('serves a later caller from the cache without a request', async () => {
    fetchAPIMock.mockResolvedValue(ENGINES_RESPONSE)
    const first = renderHook(() => useEngineCatalogue())
    await waitFor(() => expect(first.result.current.status).toBe('ready'))
    fetchAPIMock.mockClear()

    const later = renderHook(() => useEngineCatalogue())

    expect(later.result.current.status).toBe('ready')
    expect(fetchAPIMock).not.toHaveBeenCalled()
  })

  it('does not cache a failure', async () => {
    fetchAPIMock.mockRejectedValueOnce(new Error('down')).mockResolvedValue(ENGINES_RESPONSE)
    const failed = renderHook(() => useEngineCatalogue())
    await waitFor(() => expect(failed.result.current.status).toBe('error'))

    const next = renderHook(() => useEngineCatalogue())

    await waitFor(() => expect(next.result.current.status).toBe('ready'))
  })

  it('treats a response without an engines list as an empty catalogue', async () => {
    fetchAPIMock.mockResolvedValue({})

    const { result } = renderHook(() => useEngineCatalogue())

    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(result.current.engines).toEqual([])
  })
})
