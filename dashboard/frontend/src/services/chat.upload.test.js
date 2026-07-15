import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { uploadProjectFile } from './chat'
import { TOKEN_KEY } from '../api'

// uploadProjectFile bypasses fetchAPI (multipart), so its error-code
// transport needs its own adapter test (regression: codex #82 1.3).

beforeEach(() => {
  localStorage.setItem(TOKEN_KEY, 'test-token')
})

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
})

describe('uploadProjectFile error-code transport', () => {
  it('attaches the stable code from a coded 409', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ error: 'file already exists', code: 'already_exists' }),
    }))
    const file = new File(['x'], 'a.txt', { type: 'text/plain' })
    const err = await uploadProjectFile('p1', file).catch(e => e)
    expect(err.message).toBe('file already exists')
    expect(err.code).toBe('already_exists')
  })

  it('leaves code undefined on an uncoded error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 413,
      json: async () => ({ error: 'file too large' }),
    }))
    const file = new File(['x'], 'a.txt', { type: 'text/plain' })
    const err = await uploadProjectFile('p1', file).catch(e => e)
    expect(err.message).toBe('file too large')
    expect(err.code).toBeUndefined()
  })

  it('returns the node on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ path: 'a.txt' }),
    }))
    const file = new File(['x'], 'a.txt', { type: 'text/plain' })
    await expect(uploadProjectFile('p1', file)).resolves.toEqual({ path: 'a.txt' })
  })
})
