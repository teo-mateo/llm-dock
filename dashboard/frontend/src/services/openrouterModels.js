import { fetchAPI } from '../api'

// Curated OpenRouter model list. The backend returns
// { configured, current, builtin, customized } from every verb —
// `configured` is whether OPENROUTER_API_KEY is set (the chat picker hides
// the OpenRouter group when it isn't; the Tools editor stays usable).
const PATH = '/chat/settings/openrouter-models'

export const getOpenRouterModels = () => fetchAPI(PATH)

export const putOpenRouterModels = (models) =>
  fetchAPI(PATH, { method: 'PUT', body: JSON.stringify({ models }) })

export const resetOpenRouterModels = () => fetchAPI(PATH, { method: 'DELETE' })
