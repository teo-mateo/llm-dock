import { useEffect, useState } from 'react'

export default function RecreateConfirmModal({ running, onConfirm, onCancel }) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const handler = e => { if (e.key === 'Escape' && !pending) onCancel() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onCancel, pending])

  const handleConfirm = async () => {
    setPending(true)
    setError(null)
    try {
      await onConfirm()
    } catch (err) {
      setError(err.message)
      setPending(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
      onClick={() => { if (!pending) onCancel() }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="recreate-title"
        className="bg-surface rounded-lg border border-border max-w-lg w-full"
        onClick={e => e.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-border">
          <h3 id="recreate-title" className="text-lg font-semibold text-fg">Recreate container?</h3>
        </div>
        <div className="p-5 space-y-3 text-sm text-fg-muted">
          <p>
            The current container is stopped and removed, then a new one is created from the
            current compose entry (params, image, ports, volumes, env). Unlike Restart, this
            applies changes that need a new container: port mappings, network attachment,
            image and inspection.
          </p>
          <p>
            Anything kept only in the container&apos;s writable layer is lost. Bind-mounted
            state (HF cache, <code>~/.cache/maya</code>, slots, KV disk cache) is kept.
          </p>
          {running ? (
            <p data-testid="recreate-running-note" className="text-warning-fg">
              The loaded model is unloaded and reloads from scratch, which can take minutes for
              large models such as Maya or vLLM. In-flight requests and streams are cut off.
              The service will be running afterwards.
            </p>
          ) : (
            <p data-testid="recreate-stopped-note" className="text-warning-fg">
              This service is stopped. It will be created and started, so it will be running
              afterwards.
            </p>
          )}
          {error && (
            <pre role="alert" className="whitespace-pre-wrap text-danger-fg bg-danger-subtle border border-danger rounded p-2 text-xs">
              {error}
            </pre>
          )}
        </div>
        <div className="px-5 py-4 border-t border-border flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={pending}
            className="px-3 py-1.5 rounded text-xs font-medium bg-surface-muted hover:bg-surface-strong text-fg disabled:opacity-50 cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={pending}
            className="px-3 py-1.5 rounded text-xs font-medium inline-flex items-center gap-1.5 bg-warning hover:bg-warning text-white disabled:opacity-50 cursor-pointer"
          >
            {pending && <i className="fa-solid fa-spinner fa-spin"></i>}
            {pending ? 'Recreating...' : 'Recreate'}
          </button>
        </div>
      </div>
    </div>
  )
}
