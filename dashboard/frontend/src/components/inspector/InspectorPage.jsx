import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import useInspectorCaptures from '../../hooks/useInspectorCaptures'
import { deleteCapture, deleteCaptures, getCapture } from '../../services/inspector'
import CaptureList from './CaptureList'
import CaptureDetail from './CaptureDetail'

export default function InspectorPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const service = searchParams.get('service') || null
  const selectedId = searchParams.get('capture') || null

  const [live, setLive] = useState(true)
  const [confirming, setConfirming] = useState(false)
  const [deleteAllOpen, setDeleteAllOpen] = useState(false)
  const [deletingAll, setDeletingAll] = useState(false)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailMissing, setDetailMissing] = useState(false)
  const cacheRef = useRef(new Map())

  // Live refetch pauses while a delete confirm or the delete-all modal is
  // open, so the thing the user is about to delete cannot vanish under them.
  const {
    rows, total, services, loading, refreshing,
    refresh, reload, loadMore, removeRow,
  } = useInspectorCaptures({ service, live, paused: confirming || deleteAllOpen })

  const totalAll = services.reduce((sum, s) => sum + (s.capture_count || 0), 0)

  const select = (id) => {
    const next = new URLSearchParams(searchParams)
    if (id) next.set('capture', id)
    else next.delete('capture')
    setSearchParams(next, { replace: true })
  }

  const changeFilter = (value) => {
    const next = new URLSearchParams()
    if (value) next.set('service', value)
    setSearchParams(next, { replace: true })
  }

  // Detail on demand, cached by id: the conversation content of an existing
  // capture never changes, so re-selecting a row must not refetch it. A 404
  // means another tab deleted it — clear the selection and say so.
  useEffect(() => {
    if (!selectedId) {
      void Promise.resolve().then(() => {
        setDetail(null)
      })
      return undefined
    }
    const cached = cacheRef.current.get(selectedId)
    if (cached) {
      void Promise.resolve().then(() => {
        setDetail(cached)
        setDetailMissing(false)
      })
      return undefined
    }
    let cancelled = false
    void (async () => {
      setDetailLoading(true)
      try {
        const fetched = await getCapture(selectedId)
        if (cancelled) return
        cacheRef.current.set(fetched.id, fetched)
        setDetail(fetched)
        setDetailMissing(false)
      } catch {
        if (cancelled) return
        setDetail(null)
        setDetailMissing(true)
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev)
          next.delete('capture')
          return next
        }, { replace: true })
      } finally {
        if (!cancelled) setDetailLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [selectedId, setSearchParams])

  const handleRemove = (id) => {
    deleteCapture(id)
      .then(() => {
        cacheRef.current.delete(id)
        const index = rows.findIndex((row) => row.id === id)
        removeRow(id)
        if (selectedId === id) {
          const next = rows[index + 1] || rows[index - 1] || null
          select(next ? next.id : null)
        }
      })
      .catch(() => {})
  }

  const confirmDeleteAll = async () => {
    setDeletingAll(true)
    try {
      await deleteCaptures(service)
      cacheRef.current.clear()
      setDeleteAllOpen(false)
      select(null)
      reload()
    } catch {
      setDeleteAllOpen(false)
      reload()
    } finally {
      setDeletingAll(false)
    }
  }

  const switchClass = `relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
    live ? 'bg-accent' : 'bg-surface-strong'
  }`

  return (
    <div>
      <div className="flex items-center justify-between gap-4 flex-wrap mb-6">
        <h1 className="text-xl font-semibold text-fg">Inspector</h1>
        <div className="flex items-center gap-3 flex-wrap">
          <select
            value={service || ''}
            onChange={(e) => changeFilter(e.target.value)}
            className="bg-surface-strong border border-border rounded px-2 py-1.5 text-sm text-fg cursor-pointer"
            aria-label="Filter by service"
          >
            <option value="">All services ({totalAll})</option>
            {services.map((row) => (
              <option key={row.service_name} value={row.service_name}>
                {row.service_name} ({row.capture_count})
              </option>
            ))}
          </select>

          <div className="flex items-center gap-2">
            <span className="text-sm text-fg-muted">Live</span>
            <button
              type="button"
              role="switch"
              aria-checked={live}
              aria-label="Live updates"
              onClick={() => setLive((v) => !v)}
              className={switchClass}
            >
              <span
                className={`inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform ${
                  live ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          <button
            type="button"
            onClick={() => refresh()}
            className="px-2.5 py-1.5 rounded border border-border text-fg-muted hover:text-fg text-sm cursor-pointer"
          >
            <i className={`fa-solid fa-arrows-rotate mr-1.5${refreshing ? ' fa-spin' : ''}`}></i>
            Refresh
          </button>

          <button
            type="button"
            onClick={() => setDeleteAllOpen(true)}
            className="px-2.5 py-1.5 rounded bg-danger hover:bg-danger text-white text-sm cursor-pointer"
          >
            {service ? `Delete all for ${service}` : 'Delete all'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[400px_1fr] gap-6">
        <div className="bg-surface rounded-lg border border-border overflow-y-auto max-h-80 xl:max-h-[calc(100vh-220px)]">
          <CaptureList
            rows={rows}
            total={total}
            service={service}
            selectedId={selectedId}
            onSelect={select}
            onRemove={handleRemove}
            onLoadMore={() => loadMore()}
            loading={loading}
            onConfirmStateChange={setConfirming}
          />
        </div>

        <div className="bg-surface rounded-lg border border-border p-5 min-w-0">
          {detailMissing ? (
            <p className="text-sm text-fg-subtle py-10 text-center">This capture no longer exists.</p>
          ) : detail ? (
            <CaptureDetail
              key={detail.id}
              capture={detail}
              onDelete={handleRemove}
              onConfirmStateChange={setConfirming}
            />
          ) : detailLoading ? (
            <div className="animate-pulse space-y-3">
              <div className="h-5 w-48 bg-surface-strong rounded" />
              <div className="h-3 w-72 bg-surface-strong rounded" />
              <div className="h-24 w-full bg-surface-strong rounded" />
              <div className="h-24 w-full bg-surface-strong rounded" />
            </div>
          ) : (
            <p className="text-sm text-fg-subtle py-10 text-center">Select a capture to inspect it.</p>
          )}
        </div>
      </div>

      {deleteAllOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" role="dialog" aria-modal="true">
          <div className="bg-surface rounded-lg border border-border p-5 max-w-sm w-full mx-4">
            <p className="text-sm text-fg">
              Delete {total} captures? This cannot be undone.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDeleteAllOpen(false)}
                className="px-3 py-1.5 rounded border border-border text-fg-muted hover:text-fg text-sm cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDeleteAll}
                disabled={deletingAll}
                className="px-3 py-1.5 rounded bg-danger text-white text-sm font-medium cursor-pointer disabled:opacity-50"
              >
                {deletingAll ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
