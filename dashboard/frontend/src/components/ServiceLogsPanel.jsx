import { useState, useEffect, useCallback, useRef } from 'react'
import useServiceLogsSSE from '../hooks/useServiceLogsSSE'

export default function ServiceLogsPanel({ serviceName, runtime }) {
  const [paused, setPaused] = useState(false)

  const status = runtime?.status || 'not-created'
  const hasContainer = status !== 'not-created'

  const {
    text,
    lineCount,
    connected,
    error: streamError,
    reconnect,
  } = useServiceLogsSSE({
    serviceName,
    paused: !hasContainer || paused,
  })

  const logRef = useRef(null)
  const userScrolledRef = useRef(false)

  // Auto-scroll to bottom unless user scrolled up
  useEffect(() => {
    const el = logRef.current
    if (!el || userScrolledRef.current) return
    el.scrollTop = el.scrollHeight
  }, [text])

  const handleScroll = useCallback(() => {
    const el = logRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50
    userScrolledRef.current = !atBottom
  }, [])

  const handleRefresh = useCallback(() => {
    reconnect()
    userScrolledRef.current = false
  }, [reconnect])

  const handlePauseToggle = useCallback(() => {
    setPaused((prev) => !prev)
  }, [])

  const isLive = hasContainer && !paused && connected

  return (
    <div className="h-full bg-gray-800 rounded-lg border border-gray-700 flex flex-col">
      {/* Header */}
      <div className="px-5 py-3 border-b border-gray-700 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Container Logs
          </h2>
          {isLive && (
            <span
              className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse"
              aria-label="Log updates active"
            />
          )}
          {hasContainer && !paused && !connected && (
            <span
              className="w-2.5 h-2.5 rounded-full bg-yellow-500"
              aria-label="Connecting to log stream"
            />
          )}
        </div>
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
            onClick={handlePauseToggle}
            disabled={!hasContainer}
            className="p-1.5 text-gray-400 hover:text-gray-200 disabled:opacity-50 cursor-pointer"
            title={paused ? 'Resume live stream' : 'Pause live stream'}
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
      ) : streamError && streamError !== 'Service not created' ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-red-400 text-sm">
            {streamError}
          </p>
        </div>
      ) : (
        <div
          ref={logRef}
          onScroll={handleScroll}
          className="flex-1 min-h-0 overflow-auto p-4"
        >
          {text ? (
            <pre className="font-mono text-sm text-gray-300 whitespace-pre-wrap leading-relaxed select-text">
              {text}
            </pre>
          ) : (
            <p className="text-gray-500 italic text-sm">
              {connected ? 'No log output yet.' : 'Connecting...'}
            </p>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="px-5 py-2 border-t border-gray-700 text-xs text-gray-500 flex justify-between" aria-live="polite">
        <span>{lineCount} lines</span>
        <span>{paused ? 'Paused' : isLive ? 'Streaming live' : hasContainer ? 'Connecting...' : ''}</span>
      </div>
    </div>
  )
}
