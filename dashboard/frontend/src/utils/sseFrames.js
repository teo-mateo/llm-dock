function fieldValue(raw) {
  return raw.startsWith(' ') ? raw.slice(1) : raw
}

function nextLineBreak(buffer) {
  for (let i = 0; i < buffer.length; i += 1) {
    const char = buffer[i]
    if (char === '\n') return { index: i, length: 1 }
    if (char === '\r') {
      if (i + 1 >= buffer.length) return null
      if (buffer[i + 1] === '\n') return { index: i, length: 2 }
      return { index: i, length: 1 }
    }
  }
  return null
}

export function createSseParser() {
  let buffer = ''
  let event = null
  let id = null
  let dataLines = []
  let hasFields = false

  function reset() {
    event = null
    id = null
    dataLines = []
    hasFields = false
  }

  function emit(frames) {
    frames.push({
      event: event || 'message',
      id,
      data: dataLines.join('\n'),
    })
    reset()
  }

  function push(chunkText) {
    buffer += chunkText
    const frames = []
    while (true) {
      const lineBreak = nextLineBreak(buffer)
      if (lineBreak === null) break
      const line = buffer.slice(0, lineBreak.index)
      buffer = buffer.slice(lineBreak.index + lineBreak.length)

      if (line === '') {
        if (hasFields) emit(frames)
        continue
      }
      if (line.startsWith(':')) continue

      if (line.startsWith('id:')) {
        id = fieldValue(line.slice(3))
        hasFields = true
      } else if (line.startsWith('event:')) {
        event = fieldValue(line.slice(6))
        hasFields = true
      } else if (line.startsWith('data:')) {
        dataLines.push(fieldValue(line.slice(5)))
        hasFields = true
      }
    }
    return frames
  }

  return { push }
}
