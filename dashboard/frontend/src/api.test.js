import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fetchAPI, TOKEN_KEY } from './api'

// Adapter-level transport tests (regression: codex #82 1.3): the component
// tests manufacture errors that already carry `code`, so without these the
// JSON→Error.code plumbing could silently break while everything stays green.

beforeEach(() => {
  localStorage.setItem(TOKEN_KEY, 'test-token')
})

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
})

function stubFetch(response) {
  const mock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', mock)
  return mock
}

describe('fetchAPI error-code transport', () => {
  it('attaches the stable code from a coded error body', async () => {
    stubFetch({
      ok: false,
      status: 409,
      text: async () => JSON.stringify({ error: 'file changed on disk since it was loaded', code: 'revision_conflict' }),
    })
    const err = await fetchAPI('/x').catch(e => e)
    expect(err).toBeInstanceOf(Error)
    expect(err.message).toBe('file changed on disk since it was loaded')
    expect(err.code).toBe('revision_conflict')
  })

  it('leaves code undefined on an uncoded error body', async () => {
    stubFetch({
      ok: false,
      status: 400,
      text: async () => JSON.stringify({ error: 'bad path' }),
    })
    const err = await fetchAPI('/x').catch(e => e)
    expect(err.message).toBe('bad path')
    expect(err.code).toBeUndefined()
  })

  it('survives a non-JSON error body', async () => {
    stubFetch({ ok: false, status: 502, text: async () => 'gateway exploded' })
    const err = await fetchAPI('/x').catch(e => e)
    expect(err.message).toBe('HTTP 502')
    expect(err.code).toBeUndefined()
  })

  it('returns the parsed body on success', async () => {
    stubFetch({ ok: true, status: 200, json: async () => ({ ok: true }) })
    await expect(fetchAPI('/x')).resolves.toEqual({ ok: true })
  })
})

// Auth-failure redirect (regression: v2 frontend must bounce to login when the
// token is rejected). The redirect URL is a pure helper (buildLoginRedirectUrl)
// so it's tested directly; fetchAPI's 401/no-token paths are asserted via their
// observable side effect (token cleared) — jsdom can't read back a navigation.
describe('auth failure redirect', () => {
  it('builds a login URL carrying the current path back', async () => {
    const api = await import('./api')
    expect(api.buildLoginRedirectUrl('/v2/chat/abc123'))
      .toBe('http://localhost:3399/?redirect=%2Fv2%2Fchat%2Fabc123')
    expect(api.buildLoginRedirectUrl('/v2/services/foo'))
      .toBe('http://localhost:3399/?redirect=%2Fv2%2Fservices%2Ffoo')
  })

  it('clears the token and throws on 401', async () => {
    const api = await import('./api')
    localStorage.setItem(api.TOKEN_KEY, 'test-token')

    stubFetch({
      ok: false,
      status: 401,
      text: async () => JSON.stringify({ error: 'Authentication failed' }),
    })

    const err = await api.fetchAPI('/x').catch(e => e)
    expect(err.message).toBe('Authentication failed')
    expect(localStorage.getItem(api.TOKEN_KEY)).toBeNull()
  })

  it('clears the token and throws when no token is present', async () => {
    const api = await import('./api')
    localStorage.removeItem(api.TOKEN_KEY)

    const err = await api.fetchAPI('/x').catch(e => e)
    expect(err.message).toBe('Not authenticated')
    expect(localStorage.getItem(api.TOKEN_KEY)).toBeNull()
  })
})
