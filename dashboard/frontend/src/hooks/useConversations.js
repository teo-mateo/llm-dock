import { useState, useEffect, useCallback, useRef } from 'react'
import { listConversations, createConversation, deleteConversation, deleteConversations, updateConversation } from '../services/chat'

export default function useConversations() {
  const [conversations, setConversations] = useState([])
  const [loading, setLoading] = useState(true)
  const mountedRef = useRef(true)

  const refresh = useCallback(async () => {
    try {
      // Page through the full list. The sidebar groups conversations into
      // project sections, so a partial page would silently hide any
      // conversation past the first page — a project's chats could become
      // unreachable while the section claims to be empty.
      const PAGE = 200
      const first = await listConversations(PAGE, 0)
      const all = first.conversations || []
      const total = first.total ?? all.length
      while (all.length < total) {
        const page = await listConversations(PAGE, all.length)
        const batch = page.conversations || []
        if (batch.length === 0) break // total shrank mid-pagination
        all.push(...batch)
      }
      if (mountedRef.current) {
        setConversations(all)
      }
    } catch {
      // ignore
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    refresh()
    return () => { mountedRef.current = false }
  }, [refresh])

  const create = useCallback(async (data) => {
    const conv = await createConversation(data)
    await refresh()
    return conv
  }, [refresh])

  const remove = useCallback(async (id) => {
    await deleteConversation(id)
    await refresh()
  }, [refresh])

  const removeMany = useCallback(async (ids) => {
    if (!ids || ids.length === 0) return
    await deleteConversations(ids)
    await refresh()
  }, [refresh])

  const rename = useCallback(async (id, title) => {
    await updateConversation(id, { title })
    await refresh()
  }, [refresh])

  // In-place patch — used by the SSE conversation_updated handler so the
  // server-pushed auto-title lands in the sidebar without a full refetch
  // (and without racing one).
  const patchConversation = useCallback((id, patch) => {
    setConversations(prev => prev.map(c => c.id === id ? { ...c, ...patch } : c))
  }, [])

  return { conversations, loading, refresh, create, remove, removeMany, rename, patchConversation }
}
