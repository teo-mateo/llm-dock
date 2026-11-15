import { describe, it, expect } from 'vitest'
import { imagePreview, MAX_PREVIEW_BYTES } from './images'

describe('imagePreview', () => {
  it('previews raster types only', () => {
    expect(imagePreview({ mimeType: 'image/png', base64: 'QUJD' }).src).toBe('data:image/png;base64,QUJD')
    expect(imagePreview({ mimeType: 'image/jpeg', base64: 'QUJD' })).not.toBeNull()
    expect(imagePreview({ mimeType: 'image/svg+xml', base64: 'QUJD' })).toBeNull()
    expect(imagePreview({ mimeType: 'text/html', base64: 'QUJD' })).toBeNull()
  })

  it('rejects images over the size cap', () => {
    const base64 = 'A'.repeat(Math.ceil((MAX_PREVIEW_BYTES * 4) / 3) + 8)
    expect(imagePreview({ mimeType: 'image/png', base64 })).toBeNull()
  })

  it('decodes the bytes with the declared type', async () => {
    const blob = imagePreview({ mimeType: 'image/png', base64: 'QUJD' }).toBlob()
    expect(blob.type).toBe('image/png')
    expect(await blob.text()).toBe('ABC')
  })

  it('bad base64 gives no blob', () => {
    expect(imagePreview({ mimeType: 'image/png', base64: '%%%%' }).toBlob()).toBeNull()
  })
})
