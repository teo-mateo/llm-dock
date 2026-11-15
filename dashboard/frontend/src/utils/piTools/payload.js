function parseJson(raw) {
  try {
    return { ok: true, value: JSON.parse(raw) }
  } catch {
    return { ok: false, value: undefined }
  }
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function verbatim(raw) {
  return { text: raw, images: [], details: null, structured: null, isError: false }
}

function partsOfType(content, type) {
  return content.filter((part) => isObject(part) && part.type === type)
}

function envelope(root) {
  const text = partsOfType(root.content, 'text')
    .filter((part) => typeof part.text === 'string')
    .map((part) => part.text)
    .join('\n')
  const images = partsOfType(root.content, 'image')
    .filter((part) => typeof part.data === 'string')
    .map((part) => ({
      mimeType: (typeof part.mimeType === 'string' ? part.mimeType : 'image/png').toLowerCase(),
      base64: part.data.replace(/\s/g, ''),
    }))
  return {
    text,
    images,
    details: isObject(root.details) ? root.details : null,
    structured: isObject(root.structuredContent) ? root.structuredContent : null,
    isError: root.isError === true,
  }
}

export function parseToolArgs(raw) {
  if (raw == null) return null
  const { ok, value } = parseJson(raw)
  return ok && isObject(value) ? value : null
}

export function parseToolResult(raw) {
  if (raw == null) return null
  const { ok, value } = parseJson(raw)
  if (!ok) return verbatim(raw)
  if (isObject(value) && Array.isArray(value.content)) return envelope(value)
  if (typeof value === 'string') return verbatim(value)
  return verbatim(raw)
}

export function parseToolCall(rawArgs, rawOutput, parse) {
  const args = parseToolArgs(rawArgs)
  const result = parseToolResult(rawOutput)
  if (!parse) return { args, result, view: null }
  try {
    return { args, result, view: parse(args, result) ?? null }
  } catch {
    return { args, result, view: null }
  }
}

export function imageByteSize(image) {
  const body = image.base64
  const padding = body.endsWith('==') ? 2 : body.endsWith('=') ? 1 : 0
  return Math.max(0, Math.floor((body.length * 3) / 4) - padding)
}

export function imageLabel(image) {
  const bytes = imageByteSize(image)
  const size = bytes >= 1024 ? `${Math.floor(bytes / 1024)} KB` : `${bytes} B`
  return `${image.mimeType} · ${size}`
}

export function isToolError(tool) {
  return tool.item.status === 'error' || tool.result?.isError === true
}
