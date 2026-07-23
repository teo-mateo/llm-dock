import { useState, useEffect, useCallback, useRef } from 'react'
import {
  fetchPrompts,
  createPrompt,
  updatePrompt,
  deletePrompt,
  reorderPrompts,
} from '../services/chatPrompts'

export default function useChatPrompts() {
  const [prompts, setPrompts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const mountedRef = useRef(true)

  const refetch = useCallback(async () => {
    try {
      const data = await fetchPrompts()
      if (mountedRef.current) {
        setPrompts(data)
        setError(null)
      }
    } catch (e) {
      if (mountedRef.current) {
        setError(e.message || 'Failed to load prompts')
      }
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    refetch()
    return () => { mountedRef.current = false }
  }, [refetch])

  const create = useCallback(async (name, content) => {
    const optimistic = {
      id: `temp-${Date.now()}`,
      name,
      content,
      sort_order: prompts.length,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    setPrompts(prev => [...prev, optimistic])
    try {
      const created = await createPrompt(name, content)
      setPrompts(prev =>
        prev.map(p => (p.id === optimistic.id ? created : p)),
      )
      return created
    } catch (e) {
      setPrompts(prev => prev.filter(p => p.id !== optimistic.id))
      throw e
    }
  }, [prompts.length])

  const update = useCallback(async (id, name, content) => {
    const original = prompts.find(p => p.id === id)
    const optimistic = { ...original, name, content, updated_at: new Date().toISOString() }
    setPrompts(prev =>
      prev.map(p => (p.id === id ? optimistic : p)),
    )
    try {
      const updated = await updatePrompt(id, name, content)
      setPrompts(prev =>
        prev.map(p => (p.id === id ? updated : p)),
      )
      return updated
    } catch (e) {
      setPrompts(prev =>
        prev.map(p => (p.id === id ? original : p)),
      )
      throw e
    }
  }, [prompts])

  const remove = useCallback(async (id) => {
    const original = prompts
    setPrompts(prev => prev.filter(p => p.id !== id))
    try {
      await deletePrompt(id)
    } catch (e) {
      setPrompts(original)
      throw e
    }
  }, [prompts])

  const reorder = useCallback(async (ids) => {
    const original = prompts
    const optimistic = ids
      .map((id, index) => {
        const p = original.find(p => p.id === id)
        return p ? { ...p, sort_order: index } : null
      })
      .filter(Boolean)
    setPrompts(optimistic)
    try {
      await reorderPrompts(ids)
      await refetch()
    } catch (e) {
      setPrompts(original)
      throw e
    }
  }, [prompts, refetch])

  return { prompts, loading, error, refetch, create, update, remove, reorder }
}
