import { describe, it, expect, vi } from 'vitest'
import { imageBlob, imageDataUri, isPreviewable, MAX_PREVIEW_BYTES, openImage } from './images'

describe('isPreviewable', () => {
  it('accepts raster types only', () => {
    expect(isPreviewable({ mimeType: 'image/png', base64: 'QUJD' })).toBe(true)
    expect(isPreviewable({ mimeType: 'IMAGE/JPEG', base64: 'QUJD' })).toBe(true)
    expect(isPreviewable({ mimeType: 'image/svg+xml', base64: 'QUJD' })).toBe(false)
    expect(isPreviewable({ mimeType: 'text/html', base64: 'QUJD' })).toBe(false)
  })

  it('rejects images over the size cap', () => {
    const base64 = 'A'.repeat(Math.ceil((MAX_PREVIEW_BYTES * 4) / 3) + 8)
    expect(isPreviewable({ mimeType: 'image/png', base64 })).toBe(false)
  })
})

describe('imageBlob', () => {
  it('decodes the bytes with the declared type', async () => {
    const blob = imageBlob({ mimeType: 'image/png', base64: 'QUJD' })
    expect(blob.type).toBe('image/png')
    expect(await blob.text()).toBe('ABC')
  })

  it('returns null for a type it will not preview or bad base64', () => {
    expect(imageBlob({ mimeType: 'image/svg+xml', base64: 'QUJD' })).toBeNull()
    expect(imageBlob({ mimeType: 'image/png', base64: '%%%' })).toBeNull()
  })
})

describe('imageDataUri', () => {
  it('is only built for previewable images', () => {
    expect(imageDataUri({ mimeType: 'image/png', base64: 'QU JD' })).toBe('data:image/png;base64,QUJD')
    expect(imageDataUri({ mimeType: 'image/svg+xml', base64: 'QUJD' })).toBeNull()
  })
})

describe('openImage', () => {
  it('opens a blob URL and revokes it later', () => {
    vi.useFakeTimers()
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    const open = vi.fn()
    openImage({ mimeType: 'image/png', base64: 'QUJD' }, open)
    expect(open).toHaveBeenCalledWith('blob:x', '_blank', 'noopener')
    expect(URL.revokeObjectURL).not.toHaveBeenCalled()
    vi.runAllTimers()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:x')
    vi.useRealTimers()
  })

  it('never opens a type it will not preview', () => {
    const open = vi.fn()
    openImage({ mimeType: 'image/svg+xml', base64: 'QUJD' }, open)
    expect(open).not.toHaveBeenCalled()
  })
})
