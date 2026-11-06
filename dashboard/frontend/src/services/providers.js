import { fetchAPI } from '../api'

const SETTINGS = '/chat/settings/providers'

export const getProviderSettings = () => fetchAPI(SETTINGS)

export const putProvider = (id, body) =>
  fetchAPI(`${SETTINGS}/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(body) })

export const deleteProvider = (id) =>
  fetchAPI(`${SETTINGS}/${encodeURIComponent(id)}`, { method: 'DELETE' })

export const testProvider = (id) =>
  fetchAPI(`${SETTINGS}/${encodeURIComponent(id)}/test`, { method: 'POST' })

export const getProviderModels = ({ refresh = false } = {}) =>
  fetchAPI(`/chat/providers/models${refresh ? '?refresh=1' : ''}`)
