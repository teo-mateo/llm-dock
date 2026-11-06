import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { readPiStream } from '../services/piRemote'

const RECONNECT_DELAY = 3000

const initialState = { events: [], lastSeq: 0, summary: null, lagged: false }

export function applySessionEventsFrame(state, frame) {
  if (frame.event === 'events') {
    const incoming = frame.data.events || []
    const fresh = incoming.filter((event) => event.seq > state.lastSeq)
    if (fresh.length === 0) return state
    const sorted = [...fresh].sort((a, b) => a.seq - b.seq)
    const lastSeq = sorted[sorted.length - 1].seq
    return { ...state, events: [...state.events, ...sorted], lastSeq }
  }
  if (frame.event === 'session') {
    return { ...state, summary: frame.data }
  }
  if (frame.event === 'lagged') {
    return { ...state, lagged: true }
  }
  return state
}

function reducer(state, action) {
  if (action.type === 'reset') return initialState
  if (action.type !== 'frame') return state
  return applySessionEventsFrame(state, action.frame)
}

export function usePiSessionEvents(sessionId, instanceId) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState(null)

  const mountedRef = useRef(true)
  const abortControllerRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const startStreamRef = useRef(null)
  const lastSeqRef = useRef(0)

  const startStream = useCallback(async () => {
    if (!mountedRef.current || !sessionId || !instanceId) return
    if (abortControllerRef.current) abortControllerRef.current.abort()
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    const controller = new AbortController()
    abortControllerRef.current = controller
    const path = `/pi/sessions/${encodeURIComponent(sessionId)}/${encodeURIComponent(instanceId)}/stream`

    try {
      await readPiStream(path, {
        signal: controller.signal,
        lastEventId: lastSeqRef.current,
        onFrame: (frame) => {
          if (!mountedRef.current) return
          if (frame.event === 'events') {
            const fresh = (frame.data.events || []).filter(
              (event) => event.seq > lastSeqRef.current,
            )
            if (fresh.length > 0) {
              lastSeqRef.current = Math.max(...fresh.map((event) => event.seq))
            }
          }
          dispatch({ type: 'frame', frame })
          if (frame.event === 'events' || frame.event === 'session') {
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
      if (err.status === 404) {
        setError('unknown_session')
        return
      }
      if (err.status === 401) {
        setError('Authentication failed')
        return
      }
      setError(err.message)
      reconnectTimerRef.current = setTimeout(() => {
        if (mountedRef.current) startStreamRef.current()
      }, RECONNECT_DELAY)
    } finally {
      if (abortControllerRef.current === controller) abortControllerRef.current = null
    }
  }, [sessionId, instanceId])

  startStreamRef.current = startStream

  useEffect(() => {
    mountedRef.current = true
    dispatch({ type: 'reset' })
    lastSeqRef.current = 0
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
  }, [sessionId, instanceId])

  return {
    events: state.events,
    summary: state.summary,
    connected,
    error,
  }
}
