import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import useInspectorCaptures, {
  mergeReload,
  appendPage,
  PAGE_SIZE,
  LIVE_INTERVAL_MS,
} from './useInspectorCaptures'

const { listMock, servicesMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
  servicesMock: vi.fn(),
}))

vi.mock('../services/inspector', () => ({
  listCaptures: (opts) => listMock(opts),
  inspectorServices: () => servicesMock(),
}))

function page(ids, total = ids.length) {
  return {
    captures: ids.map((id) => ({ id })),
    total,
    limit: PAGE_SIZE,
    offset: 0,
  }
}

beforeEach(() => {
  listMock.mockReset()
  servicesMock.mockReset()
  listMock.mockResolvedValue(page([]))
  servicesMock.mockResolvedValue({ services: [] })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('mergeReload', () => {
  it('puts fresh rows on top, dedupes, keeps the untouched tail', () => {
    const existing = [{ id: 'b' }, { id: 'a' }, { id: 'tail' }]
    const fresh = [{ id: 'c' }, { id: 'b' }]
    expect(mergeReload(existing, fresh).map((r) => r.id)).toEqual(['c', 'b', 'a', 'tail'])
  })
})

describe('appendPage', () => {
  it('appends a later page without reordering and dedupes races', () => {
    const existing = [{ id: 'c' }, { id: 'b' }]
    const fresh = [{ id: 'b' }, { id: 'a' }]
    expect(appendPage(existing, fresh).map((r) => r.id)).toEqual(['c', 'b', 'a'])
  })
})

describe('useInspectorCaptures', () => {
  it('loads the first page on mount with the default contract', async () => {
    listMock.mockResolvedValue(page(['a', 'b'], 5))
    const { result } = renderHook(() => useInspectorCaptures({ service: null }))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(listMock).toHaveBeenCalledWith({ service: null, limit: PAGE_SIZE, offset: 0 })
    expect(result.current.rows.map((r) => r.id)).toEqual(['a', 'b'])
    expect(result.current.total).toBe(5)
  })

  it('refetches with a fresh first page when the service filter changes', async () => {
    listMock.mockResolvedValue(page(['a']))
    const { result, rerender } = renderHook(
      ({ service }) => useInspectorCaptures({ service }),
      { initialProps: { service: null } }
    )
    await waitFor(() => expect(result.current.loading).toBe(false))

    listMock.mockResolvedValue(page(['z']))
    rerender({ service: 'svc-b' })
    await waitFor(() =>
      expect(listMock).toHaveBeenLastCalledWith({ service: 'svc-b', limit: PAGE_SIZE, offset: 0 })
    )
    await waitFor(() => expect(result.current.rows.map((r) => r.id)).toEqual(['z']))
  })

  it('loadMore appends at the current row count and no-ops past the end', async () => {
    listMock.mockResolvedValueOnce(page(['a', 'b'], 3))
    const { result } = renderHook(() => useInspectorCaptures({}))
    await waitFor(() => expect(result.current.loading).toBe(false))

    listMock.mockResolvedValueOnce(page(['c'], 3))
    await act(async () => { await result.current.loadMore() })
    expect(listMock).toHaveBeenLastCalledWith({ service: null, limit: PAGE_SIZE, offset: 2 })
    expect(result.current.rows.map((r) => r.id)).toEqual(['a', 'b', 'c'])

    const callsBefore = listMock.mock.calls.length
    await act(async () => { await result.current.loadMore() })
    expect(listMock.mock.calls.length).toBe(callsBefore)
  })

  it('refresh merges so a load-more tail survives', async () => {
    listMock.mockResolvedValueOnce(page(['b', 'a'], 5))
    const { result } = renderHook(() => useInspectorCaptures({}))
    await waitFor(() => expect(result.current.loading).toBe(false))

    listMock.mockResolvedValueOnce(page(['c'], 5))
    await act(async () => { await result.current.loadMore() })
    expect(result.current.rows.map((r) => r.id)).toEqual(['b', 'a', 'c'])

    listMock.mockResolvedValueOnce(page(['d', 'b'], 5))
    await act(async () => { await result.current.refresh() })

    expect(result.current.rows.map((r) => r.id)).toEqual(['d', 'b', 'a', 'c'])
  })

  it('reload replaces the list instead of merging', async () => {
    listMock.mockResolvedValueOnce(page(['b', 'a'], 5))
    const { result } = renderHook(() => useInspectorCaptures({}))
    await waitFor(() => expect(result.current.loading).toBe(false))

    listMock.mockResolvedValueOnce(page([], 0))
    await act(async () => { result.current.reload() })

    await waitFor(() => expect(result.current.rows).toEqual([]))
    await waitFor(() => expect(result.current.total).toBe(0))
  })

  it('refetches on the live interval when live is on', async () => {
    vi.useFakeTimers()
    listMock.mockResolvedValue(page(['a'], 1))
    renderHook(() => useInspectorCaptures({ live: true }))

    await act(async () => { await Promise.resolve() })
    const initialCalls = listMock.mock.calls.length

    await act(async () => { vi.advanceTimersByTime(LIVE_INTERVAL_MS) })
    expect(listMock.mock.calls.length).toBe(initialCalls + 1)
  })

  it('does not refetch when live is off or paused', async () => {
    vi.useFakeTimers()
    listMock.mockResolvedValue(page([]))
    renderHook(() => useInspectorCaptures({ live: false, paused: true }))

    await act(async () => { await Promise.resolve() })
    const calls = listMock.mock.calls.length
    await act(async () => { vi.advanceTimersByTime(LIVE_INTERVAL_MS * 2) })

    expect(listMock.mock.calls.length).toBe(calls)
  })

  it('keeps the services list from the services endpoint', async () => {
    servicesMock.mockResolvedValue({
      services: [{ service_name: 'svc-a', capture_count: 3 }],
    })
    const { result } = renderHook(() => useInspectorCaptures({}))

    await waitFor(() => expect(result.current.services.length).toBe(1))
    expect(result.current.services[0].service_name).toBe('svc-a')
  })
})
