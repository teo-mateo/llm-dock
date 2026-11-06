import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { piSessionKey, readPiStream } from '../services/piRemote'

const RECONNECT_DELAY = 3000

const initialState = { byKey: {}, order: [] }

function sortedKeys(byKey) {
  return Object.keys(byKey).sort((a, b) => {
    const left = byKey[a]
    const right = byKey[b]
    if (left.live !== right.live) return left.live ? -1 : 1
    return (right.last_seen || 0) - (left.last_seen || 0)
  })
}

export function applySessionsFrame(state, frame) {
  if (frame.event === 'snapshot') {
    const summaries = frame.data.sessions || []
    const byKey = {}
    for (const summary of summaries) byKey[piSessionKey(summary)] = summary
    return { byKey, order: sortedKeys(byKey) }
  }
  if (frame.event === 'session') {
    const summary = frame.data
    if (!summary || !summary.session_id) return state
    const byKey = { ...state.byKey, [piSessionKey(summary)]: summary }
    return { byKey, order: sortedKeys(byKey) }
  }
  return state
}

function reducer(state, action) {
  if (action.type !== 'frame') return state
  return applySessionsFrame(state, action.frame)
}

export function usePiSessions() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState(null)

  const mountedRef = useRef(true)
  const abortControllerRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const startStreamRef = useRef(null)

  const startStream = useCallback(async () => {
    if (!mountedRef.current) return
    if (abortControllerRef.current) abortControllerRef.current.abort()
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    const controller = new AbortController()
    abortControllerRef.current = controller
    try {
      await readPiStream('/pi/sessions/stream', {
        signal: controller.signal,
        onFrame: (frame) => {
          if (!mountedRef.current) return
          if (frame.event === 'snapshot' || frame.event === 'session') {
            dispatch({ type: 'frame', frame })
            setConnected(true)
            setError(null)
          }
        },
      })
      if (!mountedRef.current || controller.signal.aborted) return
      setConnected(false)
      reconnectTimerRef.current = setTimeout(() => {
        if (mountedRef.current) startStreamRef.current()
      }, 0)
    } catch (err) {
      if (err.name === 'AbortError' || !mountedRef.current) return
      setConnected(false)
      setError(err.message)
      if (err.status === 401) return
      reconnectTimerRef.current = setTimeout(() => {
        if (mountedRef.current) startStreamRef.current()
      }, RECONNECT_DELAY)
    } finally {
      if (abortControllerRef.current === controller) abortControllerRef.current = null
    }
  }, [])

  startStreamRef.current = startStream

  useEffect(() => {
    mountedRef.current = true
    startStreamRef.current()
    return () => {
      mountedRef.current = false
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
        abortControllerRef.current = null
      }
    }
  }, [])

  return {
    sessions: state.order.map((key) => state.byKey[key]),
    connected,
    error,
  }
}
