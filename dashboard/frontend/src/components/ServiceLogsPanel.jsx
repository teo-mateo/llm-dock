import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchAPI } from '../api'

const LOG_POLL_INTERVAL = 3000
const DEFAULT_TAIL = 200
const FONT_SIZE_KEY = 'dashboard_logs_font_size'
const FONT_SIZE_MIN = 10
const FONT_SIZE_MAX = 22
const FONT_SIZE_DEFAULT = 14
const FONT_SIZE_STEP = 1

function readFontSize() {
  try {
    const v = parseInt(localStorage.getItem(FONT_SIZE_KEY), 10)
    if (Number.isFinite(v) && v >= FONT_SIZE_MIN && v <= FONT_SIZE_MAX) return v
  } catch { /* ignore */ }
  return FONT_SIZE_DEFAULT
}

export default function ServiceLogsPanel({ serviceName, runtime }) {
  const [logs, setLogs] = useState('')
  const [lineCount, setLineCount] = useState(0)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [paused, setPaused] = useState(false)
  const [logError, setLogError] = useState(null)
  const [fontSize, setFontSize] = useState(readFontSize)
  const logRef = useRef(null)
  const userScrolledRef = useRef(false)
  const mountedRef = useRef(true)

  const bumpFontSize = useCallback((delta) => {
    setFontSize(prev => {
      const next = Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, prev + delta))
      try { localStorage.setItem(FONT_SIZE_KEY, String(next)) } catch { /* ignore */ }
      return next
    })
  }, [])

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
      <div className="px-5 py-3 border-b border-gray-700 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Container Logs
          </h2>
          {hasContainer && !paused && (
            <span
              className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse"
              aria-label="Log updates active"
            />
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center text-gray-400" title="Log font size">
            <button
              onClick={() => bumpFontSize(-FONT_SIZE_STEP)}
              disabled={fontSize <= FONT_SIZE_MIN}
              className="p-1.5 hover:text-gray-200 disabled:opacity-40 cursor-pointer"
              title="Smaller text"
              aria-label="Decrease log font size"
            >
              <i className="fa-solid fa-minus text-xs"></i>
            </button>
            <span className="text-[10px] tabular-nums w-5 text-center select-none">{fontSize}</span>
            <button
              onClick={() => bumpFontSize(FONT_SIZE_STEP)}
              disabled={fontSize >= FONT_SIZE_MAX}
              className="p-1.5 hover:text-gray-200 disabled:opacity-40 cursor-pointer"
              title="Larger text"
              aria-label="Increase log font size"
            >
              <i className="fa-solid fa-plus text-xs"></i>
            </button>
          </div>
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
            <pre
              className="font-mono text-gray-300 whitespace-pre-wrap leading-relaxed select-text"
              style={{ fontSize: `${fontSize}px` }}
            >
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
