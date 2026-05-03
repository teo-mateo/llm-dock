import { useState, useEffect, useCallback, useRef } from 'react'
import { getToken, API_BASE } from '../api'

const RECONNECT_DELAY = 3000

export default function useServiceLogsSSE(serviceName, { enabled = true, tail = 200 } = {}) {
  const [lines, setLines] = useState([])
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [streamEnded, setStreamEnded] = useState(false)

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
    if (mountedRef.current) setConnected(false)
  }, [])

  const startStream = useCallback(() => {
    const token = getToken()
    if (!token) {
      if (mountedRef.current) { setError('Not authenticated'); setLoading(false) }
      return
    }

    if (abortControllerRef.current) abortControllerRef.current.abort()
    if (reconnectTimerRef.current) { clearTimeout(reconnectTimerRef.current); reconnectTimerRef.current = null }

    const controller = new AbortController()
    abortControllerRef.current = controller

    if (mountedRef.current) {
      setLines([])
      setError(null)
      setStreamEnded(false)
      setLoading(true)
      setConnected(false)
    }

    fetch(`${API_BASE}/services/${encodeURIComponent(serviceName)}/logs/stream?tail=${tail}`, {
      headers: { 'Authorization': `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(async response => {
        if (!response.ok) {
          const text = await response.text()
          let msg = `HTTP ${response.status}`
          try { msg = JSON.parse(text).error || msg } catch { /* not JSON */ }
          if (mountedRef.current) { setError(msg); setLoading(false); setConnected(false) }
          return
        }

        if (mountedRef.current) { setConnected(true); setError(null) }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let cleanEnd = false

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
                if (data.type === 'snapshot_start') { setLines([]); setLoading(true) }
                else if (data.type === 'log') setLines(prev => [...prev, data.line])
                else if (data.type === 'snapshot_end') setLoading(false)
                else if (data.type === 'stream_end') { cleanEnd = true; setStreamEnded(true); setConnected(false) }
                else if (data.type === 'error') { setError(data.message); setConnected(false) }
              } catch { /* malformed line */ }
            }
          }
        } catch (err) {
          if (err.name !== 'AbortError' && mountedRef.current) {
            setError(`Stream error: ${err.message}`)
            setConnected(false)
          }
        } finally {
          if (mountedRef.current) {
            setConnected(false)
            setLoading(false)
            // Reconnect only on unexpected drops — not clean stream_end, not user abort
            if (!controller.signal.aborted && !cleanEnd) {
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
          setLoading(false)
          reconnectTimerRef.current = setTimeout(
            () => { if (mountedRef.current) startStreamRef.current() },
            RECONNECT_DELAY,
          )
        }
      })
  }, [serviceName, tail])

  startStreamRef.current = startStream

  useEffect(() => {
    mountedRef.current = true
    if (enabled) {
      startStreamRef.current()
    } else {
      stopStream()
    }
    return () => {
      mountedRef.current = false
      stopStream()
    }
  }, [enabled, serviceName, stopStream])

  return { lines, connected, loading, error, streamEnded, refresh: startStream }
}
