const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? `${window.location.protocol}//${window.location.hostname}:3399/api`
  : `${window.location.protocol}//${window.location.hostname}/api`

const TOKEN_KEY = 'dashboard_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export async function fetchAPI(endpoint, options = {}) {
  const token = getToken()
  if (!token) throw new Error('Not authenticated')

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...options.headers
    }
  })

  if (response.status === 401) {
    localStorage.removeItem(TOKEN_KEY)
    throw new Error('Authentication failed')
  }

  if (!response.ok) {
    const text = await response.text()
    let msg = `HTTP ${response.status}`
    try {
      const data = JSON.parse(text)
      msg = typeof data.error === 'string' ? data.error : msg
    } catch { /* not JSON */ }
    throw new Error(msg)
  }

  return response.json()
}
