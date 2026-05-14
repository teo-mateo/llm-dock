import { API_BASE, getToken } from '../api'

async function request(path, options = {}) {
  const token = getToken()
  if (!token) throw new Error('Not authenticated')
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  })
  const text = await res.text()
  let body = null
  try { body = text ? JSON.parse(text) : null } catch { body = { error: text } }
  if (!res.ok) {
    // Surface structured validation errors from PUT /json so the editor
    // can render per-entry messages. Generic Error.message keeps the
    // existing throw-and-catch ergonomics elsewhere.
    const err = new Error(body?.error || `HTTP ${res.status}`)
    err.status = res.status
    err.body = body
    throw err
  }
  return body
}

export const getRegistry = () => request('/chat/mcp-registry')
export const getRegistryJson = () => request('/chat/mcp-registry/json')
export const putRegistryJson = (content) =>
  request('/chat/mcp-registry/json', { method: 'PUT', body: JSON.stringify({ content }) })
export const reloadRegistry = () =>
  request('/chat/mcp-registry/reload', { method: 'POST' })
export const testServer = (server_id, tool_name = null, args = {}) => {
  const body = { server_id }
  if (tool_name) {
    body.tool_name = tool_name
    body.arguments = args
  }
  return request('/chat/mcp-registry/test', { method: 'POST', body: JSON.stringify(body) })
}
