// Shared helpers for the curated OpenRouter model list: the client-side mirror
// of the server's PUT validation, label derivation from a catalog entry, and
// the display formatters the picker needs. Kept out of the component so the
// picker, its Advanced JSON panel, and the service layer all validate one way.

// Client-side mirror of the server validation in chat/settings_store.py, so
// Save can be gated and the error shown before a round-trip. Takes the raw
// textarea text; returns an error string or null.
export function validateModelsJson(text) {
  let parsed
  try {
    parsed = JSON.parse(text)
  } catch (e) {
    return `Invalid JSON: ${e.message}`
  }
  return validateModels(parsed)
}

// Same rules, but on an already-parsed value.
export function validateModels(parsed) {
  if (!Array.isArray(parsed)) return 'Top level must be an array of {id, label?} objects.'
  const seen = new Set()
  for (const entry of parsed) {
    if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) {
      return 'Each model must be an object with an "id".'
    }
    if (typeof entry.id !== 'string' || !entry.id.trim()) {
      return 'Each model must have a non-empty string "id".'
    }
    if (entry.label !== undefined && typeof entry.label !== 'string') {
      return '"label" must be a string when present.'
    }
    if (seen.has(entry.id.trim())) return `Duplicate model id: ${entry.id.trim()}`
    seen.add(entry.id.trim())
  }
  return null
}

export const modelsToJson = (models) => JSON.stringify(models ?? [], null, 2)

// Default label for a model added from the catalog. The server already strips
// the "Vendor: " prefix OpenRouter prefixes names with, since the vendor has a
// column of its own; fall back through name to the bare id.
export function deriveLabel(catalogEntry) {
  if (!catalogEntry) return ''
  return catalogEntry.label || catalogEntry.name || catalogEntry.id
}

// Upstream prices arrive as $/token; the normalized payload carries $/1M and
// this is the only place it becomes user-facing text. Raw 0.000000834 is
// unreadable, and a bare "0" is misleading without the "Free" wording.
export function formatPricePerMtok(value) {
  if (value === null || value === undefined) return '—'
  if (value === 0) return 'Free'
  const text = value >= 0.01 ? value.toFixed(2) : value.toPrecision(2)
  return `$${text}/M`
}

// Context length as "1M" / "200K" — the two units a picker is read at a glance.
export function formatContext(length) {
  if (!length) return '—'
  if (length >= 1_000_000) return `${(length / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  return `${Math.round(length / 1000)}K`
}

export const CONTEXT_PRESETS = [
  { label: 'any', value: 0 },
  { label: '128K+', value: 128_000 },
  { label: '256K+', value: 256_000 },
  { label: '1M+', value: 1_000_000 },
]
