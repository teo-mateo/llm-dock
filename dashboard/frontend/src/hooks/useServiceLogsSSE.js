import { useState, useEffect, useCallback, useRef } from 'react'
import { getToken, API_BASE, TOKEN_KEY } from '../api'

const DEFAULT_TAIL = 200

export default function useServiceLogsSSE({ serviceName, paused }) {
  const [lines, setLines] = useState([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState(null)
  const [snapshotDone, setSnapshotDone] = useState(false)

  const mountedRef = useRef(true)
  const abortRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const connectRef = useRef(null)

  const doConnect = useCallback(() => {
    if (!serviceName || paused) return

    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    setLines([])
    setSnapshotDone(false)
    setError(null)

    const controller = new AbortController()
    abortRef.current = controller

    const token = getToken()
    if (!token) {
      if (mountedRef.current) {
        setError('Not authenticated')
      }
      return
    }

    const url = `${API_BASE}/services/${serviceName}/logs/stream?tail=${DEFAULT_TAIL}&timestamps=true`

    fetch(url, {
      method: 'GET',
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          if (response.status === 401) {
            if (mountedRef.current) {
              localStorage.removeItem(TOKEN_KEY)
              setError('Authentication failed')
              setConnected(false)
            }
          } else if (response.status === 404) {
            if (mountedRef.current) {
              setError('Service not created')
              setConnected(false)
            }
          } else {
            if (mountedRef.current) {
              setError(`HTTP ${response.status}`)
              setConnected(false)
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

        while (true) {
          if (controller.signal.aborted) break

          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const splitLines = buffer.split('\n')
          buffer = splitLines.pop()

          for (const line of splitLines) {
            const trimmed = line.trim()
            if (!trimmed) continue
            if (trimmed.startsWith(':')) continue

            if (trimmed.startsWith('data: ')) {
              try {
                const data = JSON.parse(trimmed.slice(6))

                switch (data.type) {
                  case 'snapshot_start':
                    if (mountedRef.current) {
                      setLines([])
                    }
                    break

                  case 'log':
                    if (mountedRef.current) {
                      setLines((prev) => [...prev, data.line])
                    }
                    break

                  case 'snapshot_end':
                    if (mountedRef.current) {
                      setSnapshotDone(true)
                    }
                    break

                  case 'error':
                    if (mountedRef.current) {
                      setError(data.message || 'Stream error')
                    }
                    break

                  case 'stream_end':
                    if (mountedRef.current) {
                      setConnected(false)
                    }
                    break
                }
              } catch {
                // ignore malformed
              }
            }
          }
        }
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        if (mountedRef.current) {
          setConnected(false)
          if (err.message) {
            setError('Connection lost, reconnecting in 3s...')
          }
          reconnectTimerRef.current = setTimeout(() => {
            if (mountedRef.current && getToken()) {
              connectRef.current()
            }
          }, 3000)
        }
      })
  }, [serviceName, paused])

  // Keep ref stable so the reconnect closure can call it
  useEffect(() => {
    connectRef.current = doConnect
  }, [doConnect])

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    if (mountedRef.current) {
      setConnected(false)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connectRef.current()

    return () => {
      mountedRef.current = false
      disconnect()
    }
  }, [connectRef, disconnect])

  const text = lines.join('\n')

  return {
    text,
    lineCount: lines.length,
    connected,
    error,
    snapshotDone,
    reconnect: doConnect,
  }
}
