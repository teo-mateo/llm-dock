import { useState } from 'react'
import { Link } from 'react-router-dom'
import { relativeTime, formatDuration } from './parse'

function statusInfo(capture) {
  const code = capture.status_code
  if (code == null) return { label: '—', cls: 'text-fg-subtle' }
  if (code < 400) return { label: String(code), cls: 'bg-success-subtle text-success-fg' }
  return { label: String(code), cls: 'bg-danger-subtle text-danger-fg' }
}

function CaptureRow({ capture, selected, confirming, onSelect, onAskDelete, onConfirmDelete, onCancelConfirm }) {
  const status = statusInfo(capture)
  const truncated = capture.request_truncated || capture.response_truncated

  const handleSelect = (e) => {
    e.stopPropagation()
    onSelect(capture.id)
  }

  return (
    <div
      data-capture-id={capture.id}
      role="button"
      tabIndex={0}
      onClick={handleSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter') handleSelect(e)
      }}
      className={`group px-3 py-2 cursor-pointer border-l-2 transition-colors ${
        selected
          ? 'border-l-accent bg-surface-strong'
          : 'border-l-transparent hover:bg-surface-muted'
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={`px-1.5 py-0.5 rounded text-xs font-mono font-medium ${status.cls}`}>
          {status.label}
        </span>
        <span className="font-mono text-xs text-fg truncate" title={capture.model || '—'}>
          {capture.model || '—'}
        </span>
        {capture.error && (
          <i
            className="fa-solid fa-triangle-exclamation text-danger-fg text-xs shrink-0"
            title={capture.error}
          ></i>
        )}
        <span className="ml-auto flex items-center gap-1 shrink-0">
          {confirming ? (
            <>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onConfirmDelete() }}
                className="text-xs px-1.5 py-0.5 rounded bg-danger text-white font-medium cursor-pointer"
              >
                Delete?
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onCancelConfirm() }}
                className="text-xs px-1.5 py-0.5 rounded border border-border text-fg-muted hover:text-fg cursor-pointer"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onAskDelete() }}
                className="opacity-0 group-hover:opacity-100 focus:opacity-100 p-1 text-fg-subtle hover:text-danger-fg cursor-pointer"
                title="Delete capture"
                aria-label="Delete capture"
              >
                <i className="fa-solid fa-trash-can text-xs"></i>
              </button>
              <time
                className="text-xs text-fg-subtle"
                title={capture.created_at}
              >
                {relativeTime(capture.created_at)}
              </time>
            </>
          )}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-fg-subtle">
        <span className="truncate">{capture.service_name}</span>
        {capture.stream && (
          <i className="fa-solid fa-bolt" title="streamed response"></i>
        )}
        {capture.prompt_tokens != null || capture.completion_tokens != null ? (
          <span className="font-mono">
            {capture.prompt_tokens != null ? `↑${capture.prompt_tokens}` : ''}
            {capture.completion_tokens != null ? ` ↓${capture.completion_tokens}` : ''}
          </span>
        ) : null}
        {capture.duration_ms != null && (
          <span className="font-mono">{formatDuration(capture.duration_ms)}</span>
        )}
        {truncated && (
          <span className="px-1 py-0.5 rounded text-[10px] font-medium bg-warning-subtle text-warning-fg">
            truncated
          </span>
        )}
      </div>
    </div>
  )
}

export default function CaptureList({
  rows,
  total,
  service,
  selectedId,
  onSelect,
  onRemove,
  onLoadMore,
  loading,
  onConfirmStateChange,
}) {
  const [confirmId, setConfirmId] = useState(null)

  const handleSelect = (id) => {
    onSelect(id)
  }

  const askDelete = (id) => {
    setConfirmId(id)
    if (onConfirmStateChange) onConfirmStateChange(true)
  }

  const cancelConfirm = () => {
    setConfirmId(null)
    if (onConfirmStateChange) onConfirmStateChange(false)
  }

  const handleRemove = (id) => {
    setConfirmId(null)
    if (onConfirmStateChange) onConfirmStateChange(false)
    onRemove(id)
  }

  const handleKeyDown = (e) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    e.preventDefault()
    if (rows.length === 0) return
    const index = rows.findIndex((r) => r.id === selectedId)
    if (e.key === 'ArrowDown') {
      const next = rows[Math.min(index + 1, rows.length - 1)]
      if (next) handleSelect(next.id)
    } else {
      const start = index === -1 ? rows.length - 1 : Math.max(index - 1, 0)
      handleSelect(rows[start].id)
    }
  }

  if (!loading && rows.length === 0) {
    return (
      <div className="text-center py-10">
        <i className="fa-solid fa-magnifying-glass text-2xl text-fg-subtle mb-3"></i>
        {service ? (
          <p className="text-fg-muted text-sm">No captures for {service}.</p>
        ) : (
          <>
            <p className="text-fg-muted text-sm">No captures yet.</p>
            <p className="text-fg-subtle text-xs mt-1">
              Turn on Request inspection on a service to start recording.
            </p>
            <Link to="/" className="mt-2 inline-block text-xs text-accent-fg hover:text-accent-fg-hover hover:underline">
              Go to Services
            </Link>
          </>
        )}
      </div>
    )
  }

  return (
    <div>
      <div
        tabIndex={0}
        onKeyDown={handleKeyDown}
        className="divide-y divide-border-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
      >
        {rows.map((row) => (
          <CaptureRow
            key={row.id}
            capture={row}
            selected={row.id === selectedId}
            confirming={row.id === confirmId}
            onSelect={handleSelect}
            onAskDelete={() => askDelete(row.id)}
            onConfirmDelete={() => handleRemove(row.id)}
            onCancelConfirm={cancelConfirm}
          />
        ))}
      </div>
      <div className="flex items-center justify-between px-3 py-2 text-xs text-fg-subtle">
        <span>
          Showing {rows.length} of {total}
        </span>
        {rows.length < total && (
          <button
            type="button"
            onClick={onLoadMore}
            className="px-2 py-1 rounded border border-border text-fg-muted hover:text-fg cursor-pointer"
          >
            Load more
          </button>
        )}
      </div>
    </div>
  )
}
