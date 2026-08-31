import { fetchAPI } from '../api'

// The live OpenRouter catalog, proxied and TTL-cached by the dashboard (15 min
// server-side). `refresh` busts that cache; `detail` adds each model's
// truncated description, which is by far the heaviest field and only wanted on
// hover. The endpoint is not gated on OPENROUTER_API_KEY — upstream is public,
// so the list can be authored before the key exists.
const PATH = '/chat/settings/openrouter-catalog'

export const getOpenRouterCatalog = ({ refresh = false, detail = false } = {}) => {
  const params = new URLSearchParams()
  if (refresh) params.set('refresh', '1')
  if (detail) params.set('detail', '1')
  const query = params.toString()
  return fetchAPI(PATH + (query ? `?${query}` : ''))
}
