import { useState, useEffect, useCallback, useRef } from 'react'
import { listConversations, createConversation, deleteConversation, updateConversation } from '../services/chat'

export default function useConversations() {
  const [conversations, setConversations] = useState([])
  const [loading, setLoading] = useState(true)
  const mountedRef = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const data = await listConversations()
      if (mountedRef.current) {
        setConversations(data.conversations || [])
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

  const rename = useCallback(async (id, title) => {
    await updateConversation(id, { title })
    await refresh()
  }, [refresh])

  return { conversations, loading, refresh, create, remove, rename }
}
