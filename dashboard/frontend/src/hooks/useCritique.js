import { useState, useCallback } from 'react'
import { requestCritique } from '../services/chat'

export default function useCritique(setCritiques) {
  const [loading, setLoading] = useState({})

  const critique = useCallback(async (messageId, extraInstructions = '') => {
    setLoading(prev => ({ ...prev, [messageId]: true }))
    try {
      const result = await requestCritique(messageId, { extraInstructions })
      setCritiques(prev => ({ ...prev, [messageId]: result }))
      return result
    } catch (err) {
      throw err
    } finally {
      setLoading(prev => ({ ...prev, [messageId]: false }))
    }
  }, [setCritiques])

  return { critique, loading }
}
