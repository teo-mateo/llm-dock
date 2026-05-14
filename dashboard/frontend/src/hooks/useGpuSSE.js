import { useState, useEffect, useCallback, useRef } from 'react'
import { getToken, API_BASE } from '../api'

const RECONNECT_DELAY = 3000

/**
 * Hook for subscribing to real-time GPU stats via the /api/gpu/stream SSE
 * endpoint. Replaces the old polling loop. Each frame emitted by the
 * backend becomes a new `gpus` value.
 *
 * @returns {{ gpus: Array<Object> | null, error: string | null, connected: boolean }}
 */
export default function useGpuSSE() {
  const [gpus, setGpus] = useState(null)
  const [error, setError] = useState(null)
  const [connected, setConnected] = useState(false)

  const mountedRef = useRef(true)
  const abortControllerRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const startStreamRef = useRef(null)

  const stopStream = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
  }, [])

  const startStream = useCallback(() => {
    const token = getToken()
    if (!token) {
      if (mountedRef.current) setError('Not authenticated')
      return
    }

    if (abortControllerRef.current) abortControllerRef.current.abort()
    if (reconnectTimerRef.current) { clearTimeout(reconnectTimerRef.current); reconnectTimerRef.current = null }

    const controller = new AbortController()
    abortControllerRef.current = controller

    fetch(`${API_BASE}/gpu/stream`, {
      headers: { 'Authorization': `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(async response => {
        if (!response.ok) {
          if (mountedRef.current) {
            setError(`HTTP ${response.status}`)
            setConnected(false)
          }
          return
        }

        if (mountedRef.current) { setConnected(true); setError(null) }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        try {
          while (true) {
            if (controller.signal.aborted) break
            const { done, value } = await reader.read()
            if (done) break

            buffer += decoder.decode(value, { stream: true })
            const parts = buffer.split('\n')
            buffer = parts.pop()

            for (const line of parts) {
              if (!line.startsWith('data: ')) continue
              try {
                const data = JSON.parse(line.slice(6))
                if (!mountedRef.current) break
                if (data.error) {
                  setError(data.error)
                } else {
                  setGpus(data.gpus || [])
                  setError(null)
                }
              } catch { /* malformed line */ }
            }
          }
        } catch (err) {
          if (err.name !== 'AbortError' && mountedRef.current) {
            setError(`Stream error: ${err.message}`)
          }
        } finally {
          if (mountedRef.current) {
            setConnected(false)
            if (!controller.signal.aborted) {
              reconnectTimerRef.current = setTimeout(
                () => { if (mountedRef.current) startStreamRef.current() },
                RECONNECT_DELAY,
              )
            }
          }
        }
      })
      .catch(err => {
        if (err.name !== 'AbortError' && mountedRef.current) {
          setError(`Connection failed: ${err.message}`)
          setConnected(false)
          reconnectTimerRef.current = setTimeout(
            () => { if (mountedRef.current) startStreamRef.current() },
            RECONNECT_DELAY,
          )
        }
      })
  }, [])

  startStreamRef.current = startStream

  useEffect(() => {
    mountedRef.current = true
    startStream()
    return () => {
      mountedRef.current = false
      stopStream()
    }
  }, [startStream, stopStream])

  return { gpus, error, connected }
}
