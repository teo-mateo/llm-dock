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
