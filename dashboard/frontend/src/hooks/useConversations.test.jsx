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

describe('useConversations full-list fetch', () => {
  it('requests the entire list in ONE unlimited call — no offset pagination', async () => {
    // Regression for codex iterations 2+4 on PR #77: project grouping must
    // never operate on a partial list, and offset pagination over the
    // mutable updated_at ordering can skip or duplicate rows when
    // conversations are touched between page fetches. A single request is
    // a consistent snapshot.
    const all = Array.from({ length: 350 }, (_, i) => conv(i))
    chatApi.listConversations.mockResolvedValue({
      conversations: all,
      total: all.length,
    })

    const { result } = renderHook(() => useConversations())
    await waitFor(() => expect(result.current.conversations).toHaveLength(350))

    expect(chatApi.listConversations).toHaveBeenCalledTimes(1)
    expect(chatApi.listConversations).toHaveBeenCalledWith(-1, 0)
  })
})
