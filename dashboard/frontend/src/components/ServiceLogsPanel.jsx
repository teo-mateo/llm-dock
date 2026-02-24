import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchAPI } from '../api'

const LOG_POLL_INTERVAL = 3000
const DEFAULT_TAIL = 200

export default function ServiceLogsPanel({ serviceName, runtime }) {
  const [logs, setLogs] = useState('')
  const [lineCount, setLineCount] = useState(0)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [paused, setPaused] = useState(false)
  const [logError, setLogError] = useState(null)
  const logRef = useRef(null)
  const userScrolledRef = useRef(false)
  const mountedRef = useRef(true)

  const status = runtime?.status || 'not-created'
  const hasContainer = status !== 'not-created'

  const fetchLogs = useCallback(async () => {
    try {
      const data = await fetchAPI(`/services/${serviceName}/logs?tail=${DEFAULT_TAIL}`)
      if (mountedRef.current) {
        setLogs(data.logs || '')
        setLineCount(data.lines || 0)
        setLastUpdated(new Date())
        setLogError(null)
      }
    } catch (err) {
      if (mountedRef.current) {
        if (err.message.includes('not been created')) {
          setLogError(null)
          setLogs('')
        } else {
          setLogError(err.message)
        }
      }
    }
  }, [serviceName])

  // Unmount guard (independent of polling state)
  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  // Fetch immediately then poll
  useEffect(() => {
    if (!hasContainer || paused) return
    const initialId = setTimeout(() => {
      setLogs('')
      setLineCount(0)
      setLogError(null)
      fetchLogs()
    }, 0)
    const intervalId = setInterval(fetchLogs, LOG_POLL_INTERVAL)
    return () => { clearTimeout(initialId); clearInterval(intervalId) }
  }, [hasContainer, paused, fetchLogs])

  // Auto-scroll to bottom unless user scrolled up
  useEffect(() => {
    const el = logRef.current
    if (!el || userScrolledRef.current) return
    el.scrollTop = el.scrollHeight
  }, [logs])

  const handleScroll = useCallback(() => {
    const el = logRef.current
    if (!el) return
    // If user is within 50px of the bottom, consider it "at bottom"
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50
    userScrolledRef.current = !atBottom
  }, [])

  const handleRefresh = useCallback(() => {
    fetchLogs()
    userScrolledRef.current = false
  }, [fetchLogs])

  const formatTime = (date) => {
    if (!date) return '--:--:--'
    return date.toLocaleTimeString()
  }

  return (
    <div className="h-full bg-gray-800 rounded-lg border border-gray-700 flex flex-col">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-700 flex justify-between items-center">
        <h2 className="text-lg font-semibold text-gray-200">
          <i className="fa-solid fa-terminal mr-2 text-gray-400"></i>Container Logs
          {hasContainer && !paused && (
            <span
              className="inline-block w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse ml-3 align-middle"
              aria-label="Log updates active"
            />
          )}
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            disabled={!hasContainer}
            className="p-1.5 text-gray-400 hover:text-gray-200 disabled:opacity-50 cursor-pointer"
            title="Refresh logs"
          >
            <i className="fa-solid fa-rotate-right text-sm"></i>
          </button>
          <button
            onClick={() => setPaused(prev => !prev)}
            disabled={!hasContainer}
            className="p-1.5 text-gray-400 hover:text-gray-200 disabled:opacity-50 cursor-pointer"
            title={paused ? 'Resume auto-refresh' : 'Pause auto-refresh'}
            aria-label={paused ? 'Log updates paused' : 'Log updates active'}
          >
            <i className={`fa-solid ${paused ? 'fa-play' : 'fa-pause'} text-sm`}></i>
          </button>
        </div>
      </div>

      {/* Log content */}
      {!hasContainer ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-gray-500 italic text-sm">
            Service has not been started. Start the service to see logs.
          </p>
        </div>
      ) : logError ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-red-400 text-sm">
            Failed to load logs: {logError}
          </p>
        </div>
      ) : (
        <div
          ref={logRef}
          onScroll={handleScroll}
          className="flex-1 min-h-0 overflow-auto p-4"
        >
          {logs ? (
            <pre className="font-mono text-sm text-gray-300 whitespace-pre-wrap leading-relaxed select-text">
              {logs}
            </pre>
          ) : (
            <p className="text-gray-500 italic text-sm">No log output yet.</p>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="px-5 py-2 border-t border-gray-700 text-xs text-gray-500 flex justify-between" aria-live="polite">
        <span>Last updated: {formatTime(lastUpdated)} | {lineCount} lines</span>
        <span>{paused ? 'Paused' : 'Polling every 3s'}</span>
      </div>
    </div>
  )
}
