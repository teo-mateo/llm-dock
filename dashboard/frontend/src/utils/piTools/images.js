import { imageByteSize } from './payload'

// Blob URLs carry the dashboard's origin, so opening an SVG (or any scriptable type) in a new tab
// would run its script with access to the session token. Only raster types are ever turned into a URL.
const PREVIEWABLE_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/bmp'])
export const MAX_PREVIEW_BYTES = 6 * 1024 * 1024

export function isPreviewable(image) {
  return PREVIEWABLE_TYPES.has(image.mimeType.toLowerCase()) && imageByteSize(image) <= MAX_PREVIEW_BYTES
}

export function imageBlob(image) {
  if (!isPreviewable(image)) return null
  try {
    const binary = atob(image.base64.replace(/\s/g, ''))
    const bytes = new Uint8Array(binary.length)
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
    return new Blob([bytes], { type: image.mimeType.toLowerCase() })
  } catch {
    return null
  }
}

export function imageDataUri(image) {
  if (!isPreviewable(image)) return null
  return `data:${image.mimeType.toLowerCase()};base64,${image.base64.replace(/\s/g, '')}`
}

const OPENED_URL_LIFETIME_MS = 60_000

export function openImage(image, open = window.open) {
  const blob = imageBlob(image)
  if (blob == null) return
  const url = URL.createObjectURL(blob)
  open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), OPENED_URL_LIFETIME_MS)
}
