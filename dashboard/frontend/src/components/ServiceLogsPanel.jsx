import { useState, useEffect, useCallback, useRef } from 'react'
import useServiceLogsSSE from '../hooks/useServiceLogsSSE'

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
  const [paused, setPaused] = useState(false)
  const [fontSize, setFontSize] = useState(readFontSize)
  const logRef = useRef(null)
  const userScrolledRef = useRef(false)

  const bumpFontSize = useCallback((delta) => {
    setFontSize(prev => {
      const next = Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, prev + delta))
      try { localStorage.setItem(FONT_SIZE_KEY, String(next)) } catch { /* ignore */ }
      return next
    })
  }, [])

  const status = runtime?.status || 'not-created'
  const hasContainer = status !== 'not-created'

  const { lines, connected, loading, error, streamEnded, refresh } = useServiceLogsSSE(
    serviceName,
    { enabled: hasContainer && !paused, tail: 200 },
  )

  // Re-attach the SSE stream when the container transitions INTO 'running'.
  // The hook itself doesn't reconnect after a clean stream_end (which fires
  // when the container exits), and `enabled` doesn't change on a normal
  // stop→start cycle, so without this the panel would freeze at "Container
  // stopped" until a page reload. Also handles --force-recreate via the
  // container_id dep. The !paused guard keeps an explicit pause sticky.
  const prevStatusRef = useRef(status)
  const containerId = runtime?.container_id
  useEffect(() => {
    const prev = prevStatusRef.current
    prevStatusRef.current = status
    if (prev !== 'running' && status === 'running' && !paused) {
      refresh()
    }
  }, [status, containerId, paused, refresh])

  // Track last activity time for footer display
  const [lastUpdated, setLastUpdated] = useState(null)
  useEffect(() => {
    if (lines.length > 0) setLastUpdated(new Date())
  }, [lines.length])

  // Auto-scroll unless the user scrolled up
  useEffect(() => {
    const el = logRef.current
    if (!el || userScrolledRef.current) return
    el.scrollTop = el.scrollHeight
  }, [lines])

  const handleScroll = useCallback(() => {
    const el = logRef.current
    if (!el) return
    userScrolledRef.current = el.scrollHeight - el.scrollTop - el.clientHeight > 50
  }, [])

  const handleRefresh = useCallback(() => {
    userScrolledRef.current = false
    refresh()
  }, [refresh])

  const formatTime = (date) => date ? date.toLocaleTimeString() : '--:--:--'

  const footerStatus = () => {
    if (!hasContainer) return 'No container'
    if (paused) return 'Paused'
    if (streamEnded) return 'Container stopped'
    if (connected) return 'Live'
    if (loading) return 'Connecting…'
    return 'Reconnecting…'
  }

  return (
    <div className="h-full bg-gray-800 rounded-lg border border-gray-700 flex flex-col">
      {/* Header */}
      <div className="px-5 py-3 border-b border-gray-700 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Container Logs
          </h2>
          {hasContainer && !paused && connected && (
            <span className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse" />
          )}
          {hasContainer && !paused && !connected && !streamEnded && (
            <span className="w-2.5 h-2.5 rounded-full bg-yellow-500 animate-pulse" />
          )}
          {streamEnded && (
            <span className="text-xs text-gray-500 italic">stopped</span>
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
            disabled={!hasContainer || paused}
            className="p-1.5 text-gray-400 hover:text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            title={paused ? 'Resume to refresh' : 'Refresh logs'}
          >
            <i className="fa-solid fa-rotate-right text-sm"></i>
          </button>
          <button
            onClick={() => setPaused(prev => !prev)}
            disabled={!hasContainer}
            className="p-1.5 text-gray-400 hover:text-gray-200 disabled:opacity-50 cursor-pointer"
            title={paused ? 'Resume' : 'Pause'}
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
      ) : error ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-red-400 text-sm">Failed to load logs: {error}</p>
        </div>
      ) : (
        <div
          ref={logRef}
          onScroll={handleScroll}
          className="flex-1 min-h-0 overflow-auto p-4"
        >
          {lines.length > 0 ? (
            <pre
              className="font-mono text-gray-300 whitespace-pre-wrap leading-relaxed select-text"
              style={{ fontSize: `${fontSize}px` }}
            >
              {lines.join('\n')}
            </pre>
          ) : loading ? (
            <p className="text-gray-500 italic text-sm">Loading logs…</p>
          ) : (
            <p className="text-gray-500 italic text-sm">No log output yet.</p>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="px-5 py-2 border-t border-gray-700 text-xs text-gray-500 flex justify-between">
        <span>Last updated: {formatTime(lastUpdated)} | {lines.length} lines</span>
        <span>{footerStatus()}</span>
      </div>
    </div>
  )
}
