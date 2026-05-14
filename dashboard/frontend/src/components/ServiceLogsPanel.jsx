import { useState, useEffect, useCallback, useRef } from 'react'
import useServiceLogsSSE from '../hooks/useServiceLogsSSE'

export default function ServiceLogsPanel({ serviceName, runtime }) {
  const [paused, setPaused] = useState(false)
  const logRef = useRef(null)
  const userScrolledRef = useRef(false)

  const status = runtime?.status || 'not-created'
  const hasContainer = status !== 'not-created'

  const { lines, connected, loading, error, streamEnded, refresh } = useServiceLogsSSE(
    serviceName,
    { enabled: hasContainer && !paused, tail: 200 },
  )

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
            <pre className="font-mono text-sm text-gray-300 whitespace-pre-wrap leading-relaxed select-text">
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
