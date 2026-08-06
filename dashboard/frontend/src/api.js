export const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? `${window.location.protocol}//${window.location.hostname}:3399/api`
  : `${window.location.protocol}//${window.location.hostname}/api`

export const TOKEN_KEY = 'dashboard_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

// Login page URL derived from the API origin so it works in dev (Vite serves
// the SPA on a different port than Flask) and in prod (same origin as /api).
const LOGIN_URL = `${API_BASE.replace(/\/api$/, '')}/`

// Redirect-once guard: many hooks fire authenticated requests on mount, so a
// single 401 would otherwise trigger a redirect storm. The full-page navigation
// unloads the app, so the flag needs no reset.
let redirecting = false

/**
 * Build the login-page URL for the current path, carrying it back via
 * ?redirect= so the v1 login handlers can return the user to where they were.
 * Pure — exported for unit testing.
 */
export function buildLoginRedirectUrl(path) {
  return `${LOGIN_URL}?redirect=${encodeURIComponent(path)}`
}

/**
 * Clear the token and bounce the user to the login page (the v1 dashboard at
 * '/', whose login modal shows automatically when no token is present).
 */
export function handleAuthFailure() {
  localStorage.removeItem(TOKEN_KEY)
  if (redirecting) return
  redirecting = true
  window.location.href = buildLoginRedirectUrl(window.location.pathname + window.location.search)
}

/**
 * Explicit logout: drop the token and send the user to the login page,
 * preserving the current path so re-login returns them to where they were.
 * Unlike handleAuthFailure, this is a deliberate user action, so it always
 * navigates regardless of the redirect-once guard.
 */
export function logout() {
  localStorage.removeItem(TOKEN_KEY)
  window.location.href = buildLoginRedirectUrl(window.location.pathname + window.location.search)
}

export async function fetchAPI(endpoint, options = {}) {
  const token = getToken()
  if (!token) {
    handleAuthFailure()
    throw new Error('Not authenticated')
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...options.headers
    }
  })

  const newToken = response.headers?.get('X-TOTP-Token')
  if (newToken) {
    localStorage.setItem(TOKEN_KEY, newToken)
  }

  if (response.status === 401) {
    handleAuthFailure()
    throw new Error('Authentication failed')
  }

  if (!response.ok) {
    const text = await response.text()
    let msg = `HTTP ${response.status}`
    let code = null
    try {
      const data = JSON.parse(text)
      msg = typeof data.error === 'string' ? data.error : msg
      // Stable machine-readable identifier for errors the UI branches on
      // (e.g. 'revision_conflict', 'already_exists') — match on err.code,
      // never on the message text.
      if (typeof data.code === 'string') code = data.code
    } catch { /* not JSON */ }
    const err = new Error(msg)
    if (code) err.code = code
    throw err
  }

  return response.json()
}
