import { imageByteSize } from './payload'

// Blob URLs carry the dashboard's origin, so opening an SVG (or any scriptable type) in a new tab
// would run its script with access to the session token. Only raster types are ever turned into a URL.
const PREVIEWABLE_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/bmp'])
export const MAX_PREVIEW_BYTES = 6 * 1024 * 1024

function isPreviewable(image) {
  return PREVIEWABLE_TYPES.has(image.mimeType) && imageByteSize(image) <= MAX_PREVIEW_BYTES
}

function decode(image) {
  try {
    const binary = atob(image.base64)
    const bytes = new Uint8Array(binary.length)
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
    return new Blob([bytes], { type: image.mimeType })
  } catch {
    return null
  }
}

export function imagePreview(image) {
  if (!isPreviewable(image)) return null
  return { src: `data:${image.mimeType};base64,${image.base64}`, toBlob: () => decode(image) }
}
