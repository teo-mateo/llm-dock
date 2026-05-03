import { useState, useEffect, useCallback, useRef, useReducer } from 'react'
import { getToken, API_BASE, TOKEN_KEY } from '../api'

const RECONNECT_DELAY = 3000

const initialState = {
  services: null,
  total: 0,
  running: 0,
  stopped: 0,
}

function reducer(state, action) {
  switch (action.type) {
    case 'SNAPSHOT':
      return {
        services: action.payload.services || [],
        total: action.payload.total || 0,
        running: action.payload.running || 0,
        stopped: action.payload.stopped || 0,
      }
    case 'DELTA':
      return applyDeltaToState(state, action.payload)
    default:
      return state
  }
}

function applyDeltaToState(state, delta) {
  const services = [...state.services]
  const serviceIndex = services.findIndex(s => s.name === delta.service_name)

  if (delta.action === 'remove') {
    if (serviceIndex !== -1) {
      services.splice(serviceIndex, 1)
    }
  } else {
    const updatedService = {
      ...(serviceIndex !== -1 ? services[serviceIndex] : {}),
      name: delta.service_name,
      status: delta.status,
      container_id: delta.container_id,
    }

    if (serviceIndex !== -1) {
      services[serviceIndex] = updatedService
    } else {
      services.push(updatedService)
    }
  }

  return {
    ...state,
    services,
    total: services.length,
    running: services.filter(s => s.status === 'running').length,
    stopped: services.filter(s => s.status === 'exited' || s.status === 'not-created').length,
  }
}

/**
 * Sorts services with open-webui first, then alphabetically by name.
 * @param {Array<Object>} services - Array of service objects
 * @returns {Array<Object>} Sorted array of services
 */
export const sortServices = (services) => {
  return [...services].sort((a, b) => {
    if (a.name === 'open-webui') return -1
    if (b.name === 'open-webui') return 1
    return a.name.localeCompare(b.name)
  })
}

/**
 * Hook for subscribing to real-time service status updates via SSE.
 * Manages connection, reconnection, and state updates from the server.
 *
 * @returns {{
 *   services: Array<Object> | null,
 *   error: string | null,
 *   connected: boolean,
 *   loading: boolean,
 *   total: number,
 *   running: number,
 *   stopped: number,
 *   refresh: function
 * }} Hook return value
 */
export default function useServicesSSE() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [error, setError] = useState(null)
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(true)

  const mountedRef = useRef(true)
  const abortControllerRef = useRef(null)
  const reconnectTimerRef = useRef(null)

  // Use a ref for startStream so we can call it from closures without
  // needing it as a dependency (avoids reconnection loops and exhaustive-deps warnings).
  const startStreamRef = useRef(null)

  const handleMessage = useCallback((event) => {
    if (!event.data || !mountedRef.current) return

    try {
      const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data

      switch (data.type) {
        case 'snapshot':
          dispatch({ type: 'SNAPSHOT', payload: data.data })
          setLoading(false)
          setError(null)
          setConnected(true)
          break

        case 'delta':
          dispatch({ type: 'DELTA', payload: data })
          break

        case 'error':
          setError(data.message || 'Services stream error')
          break
      }
    } catch {
      // ignore malformed messages
    }
  }, [])

  const handleError = useCallback((err) => {
    if (mountedRef.current) {
      setConnected(false)
      setError(`Connection lost: ${err?.message || 'Unknown error'}, reconnecting...`)
    }
  }, [])

  const processStream = useCallback(async (response, controller) => {
    if (!response.ok) {
      if (response.status === 401) {
        if (mountedRef.current) {
          setError('Authentication failed')
          localStorage.removeItem(TOKEN_KEY)
          setConnected(false)
          setLoading(false)
        }
      } else {
        if (mountedRef.current) {
          setError(`HTTP ${response.status}`)
        }
      }
      return
    }

    if (mountedRef.current) {
      setConnected(true)
      setError(null)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        if (controller.signal.aborted) break

        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              handleMessage({ data })
            } catch {
              // ignore malformed line
            }
          }
          // Keepalive messages are ignored
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError' && mountedRef.current) {
        handleError(err)
      }
    } finally {
      if (mountedRef.current) {
        setConnected(false)
        if (!controller.signal.aborted) {
          reconnectTimerRef.current = setTimeout(() => {
            if (mountedRef.current && getToken()) {
              startStreamRef.current()
            }
          }, RECONNECT_DELAY)
        }
      }
    }
  }, [handleError, handleMessage])

  const startStream = useCallback(() => {
    const token = getToken()
    if (!token) {
      if (mountedRef.current) {
        setError('Not authenticated')
        setLoading(false)
      }
      return
    }

    // Clean up any existing connection
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    const controller = new AbortController()
    abortControllerRef.current = controller

    fetch(`${API_BASE}/services/stream`, {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(response => processStream(response, controller))
      .catch(err => {
        if (err.name !== 'AbortError' && mountedRef.current) {
          handleError(err)
          reconnectTimerRef.current = setTimeout(
            () => startStreamRef.current(),
            RECONNECT_DELAY,
          )
        }
      })
  }, [handleError, processStream])

  // Keep ref stable for closures that need to call startStream
  startStreamRef.current = startStream

  const stopStream = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    if (mountedRef.current) {
      setConnected(false)
    }
  }, [])

  // Handle token changes via storage event
  useEffect(() => {
    const handleStorageChange = (e) => {
      if (e.key === TOKEN_KEY) {
        if (e.newValue) {
          startStreamRef.current()
        } else {
          stopStream()
          if (mountedRef.current) setError('Not authenticated')
        }
      }
    }

    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [stopStream])

  // Start stream on mount
  useEffect(() => {
    mountedRef.current = true
    startStreamRef.current()

    // Handle page visibility changes
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        // Reconnect when tab becomes visible to ensure UI is up-to-date
        if (!abortControllerRef.current && getToken()) {
          startStreamRef.current()
        }
      }
      // Don't disconnect on hidden to maintain real-time state for background tabs
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      mountedRef.current = false
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      stopStream()
    }
  }, [stopStream])

  const sortedServices = state.services ? sortServices(state.services) : null

  return {
    services: sortedServices,
    error,
    connected,
    loading,
    total: state.total,
    running: state.running,
    stopped: state.stopped,
    refresh: startStream,
  }
}
