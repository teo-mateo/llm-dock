import { describe, it, expect, afterEach, vi } from 'vitest'
import { renderHook, waitFor, cleanup } from '@testing-library/react'
import useConversations from './useConversations'
import * as chatApi from '../services/chat'

vi.mock('../services/chat', () => ({
  listConversations: vi.fn(),
  createConversation: vi.fn(),
  deleteConversation: vi.fn(),
  deleteConversations: vi.fn(),
  updateConversation: vi.fn(),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const conv = (i) => ({ id: `c${i}`, title: `C${i}`, updated_at: '2026-01-01' })

describe('useConversations full-list pagination', () => {
  it('fetches every page so project grouping never works on a partial list', async () => {
    // 350 conversations, page size 200 → two requests.
    const all = Array.from({ length: 350 }, (_, i) => conv(i))
    chatApi.listConversations.mockImplementation(async (limit, offset) => ({
      conversations: all.slice(offset, offset + limit),
      total: all.length,
    }))

    const { result } = renderHook(() => useConversations())
    await waitFor(() => expect(result.current.conversations).toHaveLength(350))

    expect(chatApi.listConversations).toHaveBeenCalledWith(200, 0)
    expect(chatApi.listConversations).toHaveBeenCalledWith(200, 200)
  })

  it('stops when a page comes back empty even if total was stale', async () => {
    // total claims 250 but only 150 rows actually exist (rows deleted
    // between pages) — must not loop forever.
    const all = Array.from({ length: 150 }, (_, i) => conv(i))
    chatApi.listConversations.mockImplementation(async (limit, offset) => ({
      conversations: all.slice(offset, offset + limit),
      total: 250,
    }))

    const { result } = renderHook(() => useConversations())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.conversations).toHaveLength(150)
  })
})
