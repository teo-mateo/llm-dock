import { fetchAPI } from '../api'

// Per-provider detail for a batch of model ids. OpenRouter exposes provider
// names only per model (there is no bulk endpoint), so the server fans out and
// caches per id; this asks for the rows a pane is actually showing.
// MAX_PROVIDER_BATCH mirrors the server cap — sending more is a 400, not a
// larger answer.
const PATH = '/chat/settings/openrouter-catalog/endpoints'

export const MAX_PROVIDER_BATCH = 60

export const getProviderSummaries = (ids, { force = false } = {}) =>
  fetchAPI(PATH, {
    method: 'POST',
    body: JSON.stringify(force ? { ids, force: true } : { ids }),
  })
