import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import useOpenRouterModels from '../../hooks/useOpenRouterModels'
import useOpenRouterCatalog from '../../hooks/useOpenRouterCatalog'
import useModelProviders from '../../hooks/useModelProviders'
import { MAX_PROVIDER_BATCH } from '../../services/openrouterProviders'
import {
  CONTEXT_PRESETS,
  deriveLabel,
  formatContext,
  formatPricePerMtok,
  modelsToJson,
  validateModels,
  validateModelsJson,
} from '../../utils/openrouterModels'

// Picker for the curated OpenRouter list the chat dropdowns show. Left: the
// live catalog (searchable, filterable, sortable). Right: the short list, in
// dropdown order. The short list is a convenience, not an allowlist — removing
// a model here does not break conversations already using it.
//
// The list's storage shape is unchanged ([{id, label}]); everything from the
// catalog is display-time enrichment. So the collapsed JSON panel below drives
// the same state and stays the escape hatch for bulk pastes and for the case
// where OpenRouter is unreachable.

const DEFAULT_FILTERS = {
  vendors: [],
  toolsOnly: true,
  freeOnly: false,
  minContext: 0,
  maxPriceIn: null,
  modality: '',
  hideBatch: true,
  hideVariants: false,
  hideDeprecated: false,
  showNonChat: false,
}

const SORTS = [
  { id: 'name', label: 'name' },
  { id: 'newest', label: 'newest' },
  { id: 'price', label: 'price ↑' },
  { id: 'context', label: 'context ↓' },
  { id: 'intelligence', label: 'intelligence ↓' },
]

const SORTERS = {
  name: (a, b) => a.name.localeCompare(b.name),
  newest: (a, b) => (b.created || 0) - (a.created || 0),
  price: (a, b) => a.price_in - b.price_in,
  context: (a, b) => (b.context_length || 0) - (a.context_length || 0),
  intelligence: (a, b) => (b.benchmarks?.intelligence ?? -1) - (a.benchmarks?.intelligence ?? -1),
}

const PRICE_PRESETS = [
  { label: 'any', value: '' },
  { label: '≤ $1/M', value: '1' },
  { label: '≤ $5/M', value: '5' },
  { label: '≤ $20/M', value: '20' },
]

const MODALITIES = [
  { label: 'any input', value: '' },
  { label: 'vision', value: 'image' },
  { label: 'audio', value: 'audio' },
  { label: 'video', value: 'video' },
  { label: 'files', value: 'file' },
]

// Provider detail is fetched per model, so the wanted set is the rows actually
// in view, observed just past the pane's edges so rows are described by the
// time they scroll in, and flushed on a settle rather than per row crossing.
const PROVIDER_ROOT_MARGIN = '120px 0px'
const PROVIDER_FLUSH_MS = 200

const clone = (models) => (models || []).map((m) => ({ id: m.id, label: m.label ?? m.id }))

function Toggle({ checked, onChange, disabled, children }) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-fg-muted cursor-pointer select-none">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-accent-strong"
      />
      {children}
    </label>
  )
}

function Select({ label, value, onChange, options }) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-fg-muted">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-surface border border-border rounded px-1.5 py-0.5 text-xs text-fg"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  )
}

function Tag({ children, title }) {
  return (
    <span title={title} className="text-[10px] uppercase tracking-wide text-fg-subtle border border-border rounded px-1">
      {children}
    </span>
  )
}

// Spread across providers, not the model-level price: the model-level number is
// already the cheapest endpoint, so the interesting figure is how far apart the
// providers are.
function endpointPriceRange(providers) {
  const prices = providers.map((p) => p.price_in).filter((v) => typeof v === 'number')
  if (!prices.length) return ''
  const lo = Math.min(...prices)
  const hi = Math.max(...prices)
  return lo === hi ? formatPricePerMtok(lo) : `${formatPricePerMtok(lo)}–${formatPricePerMtok(hi)}`
}

function ProviderTable({ providers }) {
  return (
    <table className="w-full text-xs mt-1.5">
      <thead>
        <tr className="text-left text-fg-subtle">
          <th className="font-normal py-1">provider</th>
          <th className="font-normal py-1">quant</th>
          <th className="font-normal py-1">ctx</th>
          <th className="font-normal py-1">in / out</th>
          <th className="font-normal py-1 text-right" title="Uptime over the last 24 h">uptime</th>
        </tr>
      </thead>
      {/* Provider + quantization is not a unique row identity: one provider
          routinely lists several endpoints for one model at the same (usually
          absent, so "unknown") quantization. Indexed in the map. */}
      <tbody>
        {providers.map((p, i) => (
          <tr key={`${p.provider}-${p.quantization}-${i}`} className="border-t border-border">
            <td className="py-1 text-fg">
              {p.provider}
              {!p.tools && <span className="ml-1.5 text-fg-subtle">no tools</span>}
              {typeof p.status === 'number' && p.status !== 0 && (
                <span className="ml-1.5 text-warning-fg" title="Upstream endpoint status, reported verbatim">
                  status {p.status}
                </span>
              )}
            </td>
            <td className="py-1 text-fg-muted">{p.quantization}</td>
            <td className="py-1 text-fg-muted">{formatContext(p.context_length)}</td>
            <td className="py-1 text-fg-muted">{formatPricePerMtok(p.price_in)} / {formatPricePerMtok(p.price_out)}</td>
            <td className={`py-1 text-right ${p.uptime_1d !== null && p.uptime_1d < 99 ? 'text-warning-fg' : 'text-fg-muted'}`}>
              {p.uptime_1d === null ? '—' : `${p.uptime_1d}%`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// Provider line for one catalog row. Undefined means "not fetched yet", which
// renders nothing rather than a placeholder: the line appears once the batch
// lands, and a row that never gets one (server unreachable, or the id was
// rejected upstream) is indistinguishable from one still in flight.
function ProviderSummary({ providers }) {
  const [open, setOpen] = useState(false)
  if (!providers) return null
  if (!providers.length) {
    return <div className="mt-1 text-xs text-fg-subtle">no endpoints listed upstream</div>
  }
  const names = providers.map((p) => p.provider)
  const quants = [...new Set(providers.map((p) => p.quantization).filter((q) => q !== 'unknown'))]
  const rest = names.length - 3
  return (
    <div className="mt-1">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-1.5 text-xs text-fg-subtle hover:text-fg max-w-full"
      >
        <i className={`fa-solid ${open ? 'fa-chevron-down' : 'fa-chevron-right'} text-[9px]`}></i>
        <span className="shrink-0">{names.length === 1 ? 'provider' : `${names.length} providers`}</span>
        <span className="truncate">
          {names.length === 1 ? names[0] : `${names.slice(0, 3).join(', ')}${rest > 0 ? ` +${rest}` : ''}`}
        </span>
        {quants.length > 0 && <span className="shrink-0">· {quants.join('/')}</span>}
        <span className="shrink-0 text-fg-muted">· {endpointPriceRange(providers)}</span>
      </button>
      {open && <ProviderTable providers={providers} />}
    </div>
  )
}

function CatalogRow({ entry, added, onToggle, providers, rowRef }) {
  return (
    <div
      ref={rowRef}
      data-model-id={entry.id}
      className={`flex items-start gap-2 px-2 py-1.5 border-b border-border last:border-0 ${added ? 'opacity-60' : ''}`}
    >
      <div className="min-w-0 flex-1">
        <div className="text-sm text-fg truncate" title={entry.id}>{entry.name}</div>
        <div className="text-xs text-fg-subtle font-mono truncate">{entry.id}</div>
        <div className="flex flex-wrap items-center gap-1.5 mt-1">
          <span className="text-xs text-fg-muted">{formatContext(entry.context_length)}</span>
          <span className="text-xs text-fg-muted">{formatPricePerMtok(entry.price_in)} / {formatPricePerMtok(entry.price_out)}</span>
          {entry.free && <Tag title="Zero-priced upstream — per-unit billing is not visible here">free</Tag>}
          {entry.tools && <Tag title="Supports tool calls">tools</Tag>}
          {entry.reasoning && <Tag>reasoning</Tag>}
          {(entry.input_modalities || []).includes('image') && <Tag>vision</Tag>}
          {(entry.input_modalities || []).includes('audio') && <Tag>audio</Tag>}
          {!entry.chat_model && <Tag title="Pseudo-model or non-text output">{entry.router ? 'router' : 'non-chat'}</Tag>}
          {entry.variant && <Tag>{entry.variant}</Tag>}
          {entry.deprecated && <span className="text-xs text-warning-fg">expiring {entry.expires}</span>}
        </div>
        <ProviderSummary providers={providers} />
      </div>
      <button
        onClick={() => onToggle(entry)}
        aria-label={added ? `Remove ${entry.name} from dropdown` : `Add ${entry.name} to dropdown`}
        className={`text-xs px-2 py-1 rounded border shrink-0 ${
          added
            ? 'border-accent-strong text-accent-fg-hover bg-accent-strong/10'
            : 'border-border text-fg-muted hover:border-border-strong hover:text-fg'
        }`}
      >
        {added ? 'Added' : 'Add'}
      </button>
    </div>
  )
}

function ShortlistRow({ entry, index, count, knownIds, catalogEntry, onLabel, onMove, onRemove }) {
  const missing = knownIds.length > 0 && !knownIds.includes(entry.id)
  return (
    <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-border last:border-0">
      <div className="flex flex-col shrink-0">
        <button
          onClick={() => onMove(index, -1)}
          disabled={index === 0}
          aria-label="Move up"
          className="text-[10px] text-fg-subtle hover:text-fg disabled:opacity-30 leading-tight"
        >
          ▲
        </button>
        <button
          onClick={() => onMove(index, 1)}
          disabled={index === count - 1}
          aria-label="Move down"
          className="text-[10px] text-fg-subtle hover:text-fg disabled:opacity-30 leading-tight"
        >
          ▼
        </button>
      </div>
      <div className="min-w-0 flex-1">
        <input
          value={entry.label}
          onChange={(e) => onLabel(index, e.target.value)}
          aria-label={`Label for ${entry.id}`}
          className="w-full bg-transparent text-sm text-fg border-b border-border focus:border-accent-strong focus:outline-none"
        />
        <div className="text-xs text-fg-subtle font-mono truncate">
          {entry.id}
          {missing && <span className="ml-1.5 text-warning-fg">not in catalog</span>}
          {catalogEntry?.deprecated && <span className="ml-1.5 text-warning-fg">deprecated</span>}
        </div>
      </div>
      <button
        onClick={() => onRemove(index)}
        aria-label={`Remove ${entry.id}`}
        className="text-xs text-fg-subtle hover:text-danger-fg shrink-0 px-1"
      >
        <i className="fa-solid fa-xmark"></i>
      </button>
    </div>
  )
}

export default function OpenRouterModelsPicker() {
  const settings = useOpenRouterModels()
  const catalog = useOpenRouterCatalog()
  const data = settings.data

  const [draft, setDraft] = useState([])
  const [baseline, setBaseline] = useState('[]')
  const [jsonText, setJsonText] = useState('[]')
  const [jsonDirty, setJsonDirty] = useState(false)
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [sort, setSort] = useState('price')
  const [showFilters, setShowFilters] = useState(false)
  const [showJson, setShowJson] = useState(false)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState(null)
  const [note, setNote] = useState(null)
  const [confirmingReset, setConfirmingReset] = useState(false)
  const searchRef = useRef(null)
  // Provider detail is fetched for the rows this scroll box reports as in view:
  // `listEl` is the observer's root (held in state because the pane mounts only
  // once the catalog has landed, and the observer has to be built with it),
  // `seenIds` is the wanted set, `observeRow` registers rows as they mount.
  const [listEl, setListEl] = useState(null)
  const observerRef = useRef(null)
  const [seenIds, setSeenIds] = useState([])
  const observeRow = useCallback((el) => {
    if (el) observerRef.current?.observe(el)
  }, [])

  // Local edits win over a background refresh of the curated list; the picker
  // syncs from the server only while nothing is unsaved.
  const dirtyRef = useRef(false)
  const dirty = data ? modelsToJson(draft) !== baseline : false
  dirtyRef.current = dirty

  useEffect(() => {
    if (!data) return
    const next = modelsToJson(data.current)
    setBaseline(next)
    if (!dirtyRef.current) {
      setDraft(clone(data.current))
      setJsonText(next)
      setJsonDirty(false)
    }
  }, [data])

  // Catalog state lives in React state for the session; the server holds the
  // 15-minute cache, so the only refetch is a remount or an explicit Refresh.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 150)
    return () => clearTimeout(t)
  }, [query])

  // One IntersectionObserver per pane instance. Rows announce themselves through
  // `data-model-id`; the callback pass is debounced, so a scroll gesture costs
  // one request rather than one per row crossing. An id is queued once, which is
  // also what the hook tracks, so re-entering a row costs nothing. Without
  // IntersectionObserver (jsdom, older browsers) the picker simply has no
  // provider lines — everything else still works.
  useEffect(() => {
    if (!listEl || typeof IntersectionObserver !== 'function') return undefined
    const pending = new Set()
    const announced = new Set()
    let timer = null
    const flush = () => {
      const added = [...pending]
      pending.clear()
      setSeenIds((prev) => [...added, ...prev].slice(0, MAX_PROVIDER_BATCH))
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = entry.target.dataset.modelId
          if (entry.isIntersecting && id && !announced.has(id)) {
            announced.add(id)
            pending.add(id)
          }
        }
        if (pending.size) {
          clearTimeout(timer)
          timer = setTimeout(flush, PROVIDER_FLUSH_MS)
        }
      },
      { root: listEl, rootMargin: PROVIDER_ROOT_MARGIN },
    )
    observerRef.current = observer
    // Rows already in the pane mounted before this effect ran, so their ref
    // callback hit a null observer; pick the first screen up here.
    listEl.querySelectorAll('[data-model-id]').forEach((el) => observer.observe(el))
    return () => {
      clearTimeout(timer)
      observer.disconnect()
      observerRef.current = null
    }
  }, [listEl])

  const models = catalog.data?.models ?? []
  const knownIds = catalog.data?.known_ids ?? []
  const catalogById = useMemo(() => new Map(models.map((m) => [m.id, m])), [models])
  const selectedIds = useMemo(() => new Set(draft.map((m) => m.id)), [draft])
  const nonChatCount = useMemo(() => models.filter((m) => !m.chat_model).length, [models])
  const vendors = useMemo(() => {
    const counts = new Map()
    for (const m of models) counts.set(m.vendor, (counts.get(m.vendor) || 0) + 1)
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  }, [models])

  const visible = useMemo(() => {
    const q = debouncedQuery.trim().toLowerCase()
    const maxPrice = filters.maxPriceIn === null ? null : Number(filters.maxPriceIn)
    const out = models.filter((m) => {
      if (!filters.showNonChat && !m.chat_model) return false
      if (filters.hideBatch && m.variant === 'batch') return false
      if (filters.hideVariants && m.variant) return false
      if (filters.hideDeprecated && m.deprecated) return false
      if (filters.toolsOnly && !m.tools) return false
      if (filters.freeOnly && !m.free) return false
      if (filters.minContext && (m.context_length || 0) < filters.minContext) return false
      if (maxPrice !== null && m.price_in > maxPrice) return false
      if (filters.modality && !(m.input_modalities || []).includes(filters.modality)) return false
      if (filters.vendors.length && !filters.vendors.includes(m.vendor)) return false
      if (q && !(m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q) || m.vendor.includes(q))) return false
      return true
    })
    return [...out].sort(SORTERS[sort])
  }, [models, debouncedQuery, filters, sort])

  // Provider detail covers the rows in view, not the head of the filtered
  // list: it costs one upstream call per model, so fetching all 425 to describe
  // the two rows a user is reading would be absurd, and describing the first 60
  // regardless of scroll position would spend 60 calls on rows nobody is reading
  // while the rows they do read stayed empty. Most recently seen first, so the
  // batch cap always buys the bottom of the screen rather than the top of the
  // list; the hook keeps what it has already fetched, so an id dropping out of
  // this window only loses a row the user has not reached.
  const providerIds = useMemo(() => seenIds.slice(0, MAX_PROVIDER_BATCH), [seenIds])
  const providerDetail = useModelProviders(providerIds)

  const filtersActive = useMemo(() => modelsToJson(filters) !== modelsToJson(DEFAULT_FILTERS), [filters])
  const validationError = jsonDirty ? validateModelsJson(jsonText) : null
  const customized = !!data?.customized
  const configured = !!data?.configured
  const catalogError = catalog.error

  function setFilter(patch) {
    setFilters((f) => ({ ...f, ...patch }))
  }

  function clearFilters() {
    setFilters(DEFAULT_FILTERS)
    setQuery('')
  }

  function toggle(entry) {
    setNote(null)
    setActionError(null)
    setDraft((prev) =>
      prev.some((m) => m.id === entry.id)
        ? prev.filter((m) => m.id !== entry.id)
        : [...prev, { id: entry.id, label: deriveLabel(entry) }]
    )
  }

  function addFirstMatch() {
    const first = visible.find((m) => !selectedIds.has(m.id))
    if (first) toggle(first)
  }

  function move(index, delta) {
    setDraft((prev) => {
      const to = index + delta
      if (to < 0 || to >= prev.length) return prev
      const next = [...prev]
      ;[next[index], next[to]] = [next[to], next[index]]
      return next
    })
  }

  function setLabel(index, label) {
    setDraft((prev) => prev.map((m, i) => (i === index ? { ...m, label } : m)))
  }

  function removeAt(index) {
    setDraft((prev) => prev.filter((_, i) => i !== index))
    setNote(null)
  }

  function onJsonChange(text) {
    setJsonText(text)
    setJsonDirty(true)
    setNote(null)
    // Keep the two panes in sync: a valid JSON edit drives the picker too.
    try {
      const parsed = JSON.parse(text)
      if (!validateModels(parsed)) setDraft(clone(parsed))
    } catch {
      /* error surfaces through validationError */
    }
  }

  function applyPayload(d) {
    const next = modelsToJson(d.current)
    setBaseline(next)
    setDraft(clone(d.current))
    setJsonText(next)
    setJsonDirty(false)
  }

  async function handleSave() {
    if (validationError) return
    setBusy(true)
    setActionError(null)
    setNote(null)
    try {
      applyPayload(await settings.save(draft))
      setNote('Saved')
    } catch (e) {
      setActionError(e.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleReset() {
    setBusy(true)
    setActionError(null)
    setNote(null)
    try {
      applyPayload(await settings.reset())
      setNote('Reset to built-in')
    } catch (e) {
      setActionError(e.message || 'Reset failed')
    } finally {
      setBusy(false)
      setConfirmingReset(false)
    }
  }

  function handleDiscard() {
    if (!data) return
    setDraft(clone(data.current))
    setJsonText(modelsToJson(data.current))
    setJsonDirty(false)
    setActionError(null)
    setNote(null)
    setConfirmingReset(false)
  }

  const vendorFilter = (
    <div className="max-h-36 overflow-y-auto border border-border rounded p-2 grid grid-cols-2 gap-x-3 gap-y-1">
      {vendors.map(([vendor, count]) => (
        <Toggle
          key={vendor}
          checked={filters.vendors.includes(vendor)}
          onChange={(on) =>
            setFilter({ vendors: on ? [...filters.vendors, vendor] : filters.vendors.filter((v) => v !== vendor) })
          }
        >
          <span className="font-mono">{vendor}</span>
          <span className="text-fg-subtle">{count}</span>
        </Toggle>
      ))}
    </div>
  )

  return (
    <div className="border border-border rounded bg-app">
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-b border-border">
        <div className="text-sm text-fg-muted">
          <i className="fa-solid fa-cloud mr-2 text-fg-subtle"></i>
          OpenRouter models
          <span className="ml-2 text-xs text-fg-subtle">{draft.length} in dropdown</span>
          {customized && (
            <span className="ml-2 text-xs text-warning-fg border border-warning rounded px-1.5 py-0.5">
              Modified from built-in
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {note && <span className="text-xs text-success-fg">{note}</span>}
          {dirty && <span className="text-xs text-warning-fg">Unsaved</span>}
          <button
            onClick={() => catalog.refresh(true)}
            disabled={catalog.loading}
            title="Re-fetch the catalog from OpenRouter, bypassing the server cache"
            className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong disabled:opacity-50"
          >
            <i className={`fa-solid fa-rotate mr-1 ${catalog.loading ? 'fa-spin' : ''}`}></i>Refresh
          </button>

          {confirmingReset ? (
            <>
              <span className="text-xs text-fg-muted">Reset to built-in?</span>
              <button
                onClick={handleReset}
                disabled={busy}
                className="text-xs px-2 py-1 rounded bg-danger hover:bg-danger text-white disabled:opacity-50"
              >
                Confirm reset
              </button>
              <button
                onClick={() => setConfirmingReset(false)}
                disabled={busy}
                className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong disabled:opacity-50"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleDiscard}
                disabled={busy || !dirty}
                className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong disabled:opacity-50"
              >
                Discard
              </button>
              <button
                onClick={() => { setConfirmingReset(true); setActionError(null); setNote(null) }}
                disabled={busy || !customized}
                title={customized ? 'Discard the customization and revert to the built-in list' : 'Already using the built-in list'}
                className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong disabled:opacity-50"
              >
                Reset to built-in
              </button>
              <button
                onClick={handleSave}
                disabled={busy || !dirty || !!validationError || !data}
                className="text-xs px-2 py-1 rounded bg-accent-strong hover:bg-accent-hover disabled:opacity-50 text-white"
              >
                Save
              </button>
            </>
          )}
        </div>
      </div>

      <p className="px-3 pt-2 text-xs text-fg-subtle">
        Models offered in the chat model pickers, curated from the live OpenRouter catalog
        {catalog.data ? ` (${catalog.data.count} models, fetched ${catalog.data.fetched_at})` : ''}.
        Removing a model here does not break conversations already using it.
      </p>

      {!configured && !settings.loading && (
        <div className="mx-3 mt-2 text-xs text-warning-fg bg-app border border-warning rounded px-3 py-2">
          <i className="fa-solid fa-triangle-exclamation mr-1"></i>
          <span className="font-mono">OPENROUTER_API_KEY</span> is not set in{' '}
          <span className="font-mono">dashboard/.env</span> — these models won't appear in the chat picker until it is.
        </div>
      )}

      {catalogError && (
        <div className="mx-3 mt-2 text-xs text-danger-fg bg-app border border-danger rounded px-3 py-2 flex items-center justify-between gap-2">
          <span>
            <i className="fa-solid fa-triangle-exclamation mr-1"></i>
            Couldn't reach the OpenRouter catalog: {catalogError}
            {catalog.data ? ' — showing the last fetched catalog.' : ' — the short list below is still editable.'}
          </span>
          <button
            onClick={() => catalog.refresh(true)}
            className="text-xs px-2 py-1 rounded border border-border text-fg-muted hover:text-fg shrink-0"
          >
            Retry
          </button>
        </div>
      )}

      {catalog.data?.stale && !catalogError && (
        <div className="mx-3 mt-2 text-xs text-warning-fg bg-app border border-warning rounded px-3 py-2">
          <i className="fa-solid fa-clock-rotate-left mr-1"></i>
          Catalog is stale ({catalog.data.error}) — showing the last good fetch.
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-3 p-3">
        <div className="border border-border rounded bg-app min-w-0">
          <div className="flex items-center gap-2 px-2 py-2 border-b border-border">
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') addFirstMatch() }}
              placeholder="Search id, name, vendor…"
              aria-label="Search models"
              className="flex-1 min-w-0 bg-surface text-fg text-sm px-2 py-1 rounded border border-border focus:border-accent-strong focus:outline-none"
            />
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              aria-label="Sort models"
              className="bg-surface border border-border rounded px-1.5 py-1 text-xs text-fg"
            >
              {SORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
            <button
              onClick={() => setShowFilters((v) => !v)}
              className="text-xs px-2 py-1 rounded border border-border text-fg-muted hover:text-fg"
            >
              Filters
            </button>
          </div>

          {showFilters && (
            <div className="px-2 py-2 border-b border-border space-y-2">
              {vendorFilter}
              <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                <Toggle checked={filters.toolsOnly} onChange={(v) => setFilter({ toolsOnly: v })}>tool-capable</Toggle>
                <Toggle checked={filters.freeOnly} onChange={(v) => setFilter({ freeOnly: v })}>free only</Toggle>
                <Toggle checked={filters.hideBatch} onChange={(v) => setFilter({ hideBatch: v })}>hide :batch</Toggle>
                <Toggle checked={filters.hideVariants} onChange={(v) => setFilter({ hideVariants: v })}>hide variants</Toggle>
                <Toggle checked={filters.hideDeprecated} onChange={(v) => setFilter({ hideDeprecated: v })}>hide expiring</Toggle>
                <Toggle checked={filters.showNonChat} onChange={(v) => setFilter({ showNonChat: v })}>
                  show {nonChatCount} non-chat
                </Toggle>
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                <Select
                  label="ctx"
                  value={String(filters.minContext)}
                  onChange={(v) => setFilter({ minContext: Number(v) })}
                  options={CONTEXT_PRESETS.map((p) => ({ label: p.label, value: String(p.value) }))}
                />
                <Select
                  label="price"
                  value={filters.maxPriceIn === null ? '' : String(filters.maxPriceIn)}
                  onChange={(v) => setFilter({ maxPriceIn: v === '' ? null : v })}
                  options={PRICE_PRESETS}
                />
                <Select
                  label="input"
                  value={filters.modality}
                  onChange={(v) => setFilter({ modality: v })}
                  options={MODALITIES}
                />
                {filtersActive && (
                  <button onClick={clearFilters} className="text-xs text-accent-fg-hover hover:underline">
                    clear filters
                  </button>
                )}
              </div>
            </div>
          )}

          {catalog.loading && !models.length ? (
            <div className="px-3 py-6 text-sm text-fg-subtle">
              <i className="fa-solid fa-spinner fa-spin mr-2"></i>Loading catalog…
            </div>
          ) : (
            <div className="max-h-[26rem] overflow-y-auto" ref={setListEl}>
              {visible.map((entry) => (
                <CatalogRow
                  key={entry.id}
                  entry={entry}
                  added={selectedIds.has(entry.id)}
                  onToggle={toggle}
                  providers={providerDetail.byId[entry.id]}
                  rowRef={observeRow}
                />
              ))}
              {!visible.length && (
                <div className="px-3 py-6 text-sm text-fg-subtle">
                  No models match. {filtersActive ? 'Clear the filters.' : ''}
                </div>
              )}
            </div>
          )}

          <div className="px-2 py-1.5 border-t border-border text-xs text-fg-subtle flex items-center justify-between">
            <span>
              showing {visible.length} of {models.length}
              {providerDetail.loading && <span className="ml-2">· loading providers…</span>}
            </span>
            <span className="flex items-center gap-3">
              {providerDetail.error && (
                <button onClick={providerDetail.retry} className="text-warning-fg hover:underline">
                  providers unavailable — retry
                </button>
              )}
              {filtersActive && (
                <button onClick={clearFilters} className="text-accent-fg-hover hover:underline">clear filters</button>
              )}
            </span>
          </div>
        </div>

        <div className="border border-border rounded bg-app min-w-0">
          <div className="px-2 py-2 border-b border-border text-sm text-fg-muted">
            Chat dropdown ({draft.length})
          </div>
          <div className="max-h-[26rem] overflow-y-auto">
            {draft.map((entry, index) => (
              <ShortlistRow
                key={entry.id}
                entry={entry}
                index={index}
                count={draft.length}
                knownIds={knownIds}
                catalogEntry={catalogById.get(entry.id)}
                onLabel={setLabel}
                onMove={move}
                onRemove={removeAt}
              />
            ))}
            {!draft.length && (
              <div className="px-3 py-6 text-sm text-fg-subtle">
                No OpenRouter models in the dropdown. Add some on the left, or Save an empty list to hide the group.
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="px-3 pb-3">
        <button
          onClick={() => setShowJson((v) => !v)}
          className="text-xs text-fg-subtle hover:text-fg"
        >
          <i className={`fa-solid ${showJson ? 'fa-chevron-down' : 'fa-chevron-right'} mr-1`}></i>
          Advanced: edit JSON
        </button>
        {showJson && (
          <>
            <textarea
              value={jsonText}
              onChange={(e) => onJsonChange(e.target.value)}
              spellCheck={false}
              disabled={busy}
              aria-label="Curated models as JSON"
              className="w-full h-40 bg-surface-muted text-fg font-mono text-xs p-3 mt-2 focus:outline-none resize-y disabled:opacity-60"
              placeholder='[{"id": "anthropic/claude-sonnet-5", "label": "Claude Sonnet 5"}]'
            />
            {validationError && (
              <div className="mt-1 text-xs text-warning-fg">
                <i className="fa-solid fa-triangle-exclamation mr-1"></i>{validationError}
              </div>
            )}
          </>
        )}
      </div>

      {(settings.error || actionError) && (
        <div className="px-3 py-2 border-t border-border text-xs space-y-1">
          {settings.error && (
            <div className="text-danger-fg"><i className="fa-solid fa-triangle-exclamation mr-1"></i>{settings.error}</div>
          )}
          {actionError && (
            <div className="text-danger-fg"><i className="fa-solid fa-triangle-exclamation mr-1"></i>{actionError}</div>
          )}
        </div>
      )}
    </div>
  )
}
