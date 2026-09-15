import { useEffect, useRef, useState } from 'react'
import useSamplingFields from '../../hooks/useSamplingFields'

// Per-conversation sampling control, in the composer's rail next to the reasoning
// level. Deliberately a different concept from that control: a level is an
// instruction to the chat template and shows no numbers; this one is the sampler's
// own numbers and shows nothing else.
//
// Offers only what the server says the selected service takes, read from the same
// module that builds the request — a knob the engine would drop is not offered,
// because an ignored parameter is indistinguishable from a model that ignored it.
// Saving replaces the whole set: merge semantics for an open knob set is where
// "why did my temperature change" bugs live.

const HINT =
  'Sampling parameters for this conversation. Applies to the next message you send; '
  + 'a field left out is not sent at all, which is the model default.'

const STORAGE_HINT = 'Storage is per conversation, not per model: switching models drops what the new one cannot take.'

function parseField(field, raw) {
  if (field.kind === 'strings') {
    const parts = raw.split(',').map(s => s.trim()).filter(Boolean)
    if (!parts.length) return { error: `${field.label}: no sequences given` }
    if (parts.length > (field.max || 4)) return { error: `${field.label}: at most ${field.max} sequences` }
    if (parts.some(p => p.length > 128)) return { error: `${field.label}: sequences up to 128 chars` }
    return { value: parts }
  }
  const num = Number(raw)
  if (raw === '' || Number.isNaN(num)) return { error: `${field.label}: not a number` }
  if (field.kind === 'integer' && !Number.isInteger(num)) return { error: `${field.label}: whole number` }
  if (field.min !== null && field.min !== undefined && num < field.min) return { error: `${field.label}: min ${field.min}` }
  if (field.max !== null && field.max !== undefined && num > field.max) return { error: `${field.label}: max ${field.max}` }
  return { value: num }
}

function toText(field, value) {
  if (value === undefined || value === null) return ''
  if (field.kind === 'strings') return Array.isArray(value) ? value.join(', ') : String(value)
  return String(value)
}

export default function SamplingParamsControl({ mainService, value, onChange, disabled }) {
  const { fields, loading, error, refresh } = useSamplingFields(mainService)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState({})
  const [errors, setErrors] = useState({})
  const rootRef = useRef(null)
  const triggerRef = useRef(null)

  const stored = value && typeof value === 'object' ? value : null
  const storedCount = stored ? Object.keys(stored).length : 0
  // Stored params whose engine takes none of them: visible and clearable, so a
  // model switch cannot leave a setting that is neither shown nor removable.
  const unsupported = storedCount > 0 && fields.length === 0 && !loading && !error

  useEffect(() => {
    if (!open) return undefined
    const onPointerDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    const onKeyDown = (e) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      setOpen(false)
      triggerRef.current?.focus()
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown, true)
    }
  }, [open])

  // Nothing to offer, nothing stored and no failure to report: no control. An
  // empty control on a model with no verified sampling interface would read as a
  // broken picker, but a failed load is not a property of the model, so an error
  // keeps the control alive.
  if (!onChange || !mainService || loading || (!fields.length && !storedCount && !error)) return null

  const openPanel = () => {
    const next = {}
    fields.forEach(f => { next[f.name] = toText(f, stored ? stored[f.name] : undefined) })
    setDraft(next)
    setErrors({})
    setOpen(true)
  }

  const apply = () => {
    const nextErrors = {}
    const out = {}
    fields.forEach(f => {
      const raw = draft[f.name]
      if (raw === undefined || raw === '') return
      const parsed = parseField(f, raw)
      if (parsed.error) nextErrors[f.name] = parsed.error
      else out[f.name] = parsed.value
    })
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    // Whole-blob replace, and null rather than {} for "nothing set", so one empty
    // state exists on the server instead of two.
    onChange(Object.keys(out).length ? out : null)
    setOpen(false)
    triggerRef.current?.focus()
  }

  const clearAll = () => {
    onChange(null)
    setOpen(false)
    triggerRef.current?.focus()
  }

  const triggerTitle = unsupported
    ? `${storedCount} sampling parameter(s) stored, but ${mainService} takes none of them, so none is sent. ${STORAGE_HINT}`
    : `${HINT} Currently set: ${storedCount || 'none'}.`

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        data-testid="sampling-params-control"
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`Sampling parameters: ${storedCount || 'none set'}`}
        title={triggerTitle}
        onClick={() => (open ? setOpen(false) : unsupported ? clearAll() : openPanel())}
        className={[
          'h-10 shrink-0 flex items-center gap-1.5 rounded-md border px-2.5 leading-none text-xs transition-colors',
          'bg-elevated border-hairline hover:border-accent hover:text-accent',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50',
          unsupported ? 'text-critique' : 'text-fg-muted',
        ].join(' ')}
      >
        <i className={`fa-solid ${unsupported ? 'fa-triangle-exclamation' : 'fa-sliders'}`} aria-hidden="true"></i>
        <span className="min-w-0 truncate">
          {unsupported ? 'sampling unused' : storedCount ? `sampling · ${storedCount}` : 'sampling'}
        </span>
        <i className="fa-solid fa-chevron-down text-[9px] opacity-60" aria-hidden="true"></i>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Sampling parameters"
          className="absolute right-0 bottom-[calc(100%+6px)] z-30 w-[300px] max-h-[60vh] overflow-auto rounded-lg border border-border bg-surface shadow-lg p-3"
        >
          {error && (
            <div className="mb-2 flex items-start gap-2">
              <i className="fa-solid fa-circle-exclamation text-critique mt-0.5" aria-hidden="true"></i>
              <div className="text-xs text-critique">
                {error}{' '}
                <button type="button" onClick={refresh} className="underline">Retry</button>
              </div>
            </div>
          )}
          {!error && !fields.length && (
            <p className="text-xs text-fg-muted mb-2">
              This model has no verified sampling interface, so nothing is sent and nothing is offered.
            </p>
          )}
          <div className="grid gap-2">
            {fields.map(f => (
              <div key={f.name} className="grid grid-cols-[minmax(0,1fr)_92px] items-center gap-2">
                <label htmlFor={`sampling-field-${f.name}`} className="text-xs text-fg-muted truncate">
                  {f.label}
                  <span className="text-fg-subtle"> · {f.min !== null && f.min !== undefined ? f.min : '–'}…{f.max !== null && f.max !== undefined ? f.max : '–'}</span>
                </label>
                <input
                  id={`sampling-field-${f.name}`}
                  data-testid={`sampling-field-${f.name}`}
                  type={f.kind === 'strings' ? 'text' : 'number'}
                  step={f.kind === 'number' ? (f.step || 'any') : '1'}
                  min={f.kind === 'strings' ? undefined : f.min}
                  max={f.kind === 'strings' ? undefined : f.max}
                  placeholder={f.kind === 'strings' ? 'up to 4, comma separated' : 'unset'}
                  value={draft[f.name] ?? ''}
                  disabled={disabled}
                  onChange={e => setDraft(prev => ({ ...prev, [f.name]: e.target.value }))}
                  className={['w-full rounded border px-2 py-1 text-xs bg-elevated text-fg',
                    errors[f.name] ? 'border-critique' : 'border-hairline'].join(' ')}
                />
                {errors[f.name] && (
                  <span className="col-span-2 text-[10px] text-critique" data-testid={`sampling-error-${f.name}`}>
                    {errors[f.name]}
                  </span>
                )}
              </div>
            ))}
          </div>
          <p className="mt-2 text-[10px] text-fg-subtle">{HINT} {STORAGE_HINT}</p>
          <div className="mt-2 flex items-center justify-end gap-2">
            {storedCount > 0 && (
              <button
                type="button"
                data-testid="sampling-clear"
                onClick={clearAll}
                className="h-8 rounded-md border border-hairline px-2 text-xs text-fg-muted hover:text-critique hover:border-critique"
              >
                Clear
              </button>
            )}
            <button
              type="button"
              data-testid="sampling-apply"
              onClick={apply}
              className="h-8 rounded-md border border-accent bg-accent/10 px-3 text-xs text-accent hover:bg-accent/20"
            >
              Apply
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
