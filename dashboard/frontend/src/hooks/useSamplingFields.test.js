import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, cleanup } from '@testing-library/react'
import useSamplingFields, { invalidateSamplingFields } from './useSamplingFields'

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))
vi.mock('../services/samplingFields', () => ({ getSamplingFields: (svc) => mockGet(svc) }))

const payload = (engine, names) => ({
  engine,
  fields: names.map(n => ({ name: n, label: n, kind: 'number', min: 0, max: 2, step: 0.1 })),
})

beforeEach(() => {
  cleanup()
  invalidateSamplingFields()
  mockGet.mockReset()
})

describe('useSamplingFields', () => {
  it('loads the fields for the service it is given', async () => {
    mockGet.mockResolvedValue(payload('vllm', ['temperature', 'seed']))
    const { result } = renderHook(() => useSamplingFields('vllm-a'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(mockGet).toHaveBeenCalledWith('vllm-a')
    expect(result.current.engine).toBe('vllm')
    expect(result.current.fields.map(f => f.name)).toEqual(['temperature', 'seed'])
  })

  it('serves a second mount from cache without a second request', async () => {
    // Two composers can be alive at once, and the answer is per-engine static data.
    mockGet.mockResolvedValue(payload('vllm', ['temperature']))
    const first = renderHook(() => useSamplingFields('vllm-b'))
    await waitFor(() => expect(first.result.current.loading).toBe(false))
    const second = renderHook(() => useSamplingFields('vllm-b'))
    await waitFor(() => expect(second.result.current.fields.length).toBe(1))
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('reports an engine with no mapping as no fields, not as an error', async () => {
    mockGet.mockResolvedValue(payload(null, []))
    const { result } = renderHook(() => useSamplingFields('ds4-c'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.fields).toEqual([])
    expect(result.current.error).toBeNull()
  })

  it('surfaces a failed load as an error rather than as an empty field list', async () => {
    // An empty list reads as "this model has no knobs". A dashboard that is
    // unreachable is a different fact and must not be reported as one.
    mockGet.mockRejectedValue(new Error('HTTP 503'))
    const { result } = renderHook(() => useSamplingFields('vllm-c'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe('HTTP 503')
    expect(result.current.fields).toEqual([])
  })

  it('does not cache a failure, so a retry can succeed', async () => {
    mockGet.mockRejectedValueOnce(new Error('HTTP 503')).mockResolvedValue(payload('vllm', ['temperature']))
    const { result } = renderHook(() => useSamplingFields('vllm-d'))
    await waitFor(() => expect(result.current.error).toBe('HTTP 503'))
    await result.current.refresh()
    await waitFor(() => expect(result.current.fields.length).toBe(1))
  })

  it('answers nothing for no service', async () => {
    const { result } = renderHook(() => useSamplingFields(null))
    expect(result.current.fields).toEqual([])
    expect(result.current.loading).toBe(false)
    expect(mockGet).not.toHaveBeenCalled()
  })
})
