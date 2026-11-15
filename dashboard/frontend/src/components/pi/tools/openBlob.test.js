import { describe, it, expect, vi } from 'vitest'
import { openBlob } from './openBlob'

function deps() {
  const scheduled = []
  return {
    scheduled,
    open: vi.fn(),
    createUrl: vi.fn(() => 'blob:x'),
    revokeUrl: vi.fn(),
    schedule: (fn, ms) => scheduled.push({ fn, ms }),
  }
}

describe('openBlob', () => {
  it('opens a URL for the blob and revokes it a minute later', () => {
    const d = deps()
    openBlob(new Blob(['x']), d)
    expect(d.open).toHaveBeenCalledWith('blob:x')
    expect(d.revokeUrl).not.toHaveBeenCalled()
    expect(d.scheduled[0].ms).toBe(60_000)
    d.scheduled[0].fn()
    expect(d.revokeUrl).toHaveBeenCalledWith('blob:x')
  })

  it('does nothing without a blob', () => {
    const d = deps()
    openBlob(null, d)
    expect(d.createUrl).not.toHaveBeenCalled()
    expect(d.open).not.toHaveBeenCalled()
  })
})
