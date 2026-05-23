import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react'
import ChatInput, { pickFence } from './ChatInput'

afterEach(() => cleanup())

// Controllable FileReader: tests resolve reads explicitly so we can assert
// behavior in the gap between file-pick and onload.
class ControllableFileReader {
  constructor() {
    this.onload = null
    this.onerror = null
    this.result = null
    ControllableFileReader.instances.push(this)
  }
  readAsText() {
    // Caller invokes resolve()/reject() to settle.
  }
  resolve(text) {
    this.result = text
    if (this.onload) this.onload({ target: this })
  }
  reject() {
    if (this.onerror) this.onerror({ target: this })
  }
}
ControllableFileReader.instances = []

let originalFileReader
beforeEach(() => {
  ControllableFileReader.instances = []
  originalFileReader = globalThis.FileReader
  globalThis.FileReader = ControllableFileReader
})
afterEach(() => {
  globalThis.FileReader = originalFileReader
})

function pickFile(file) {
  // Find the hidden <input type="file" /> and dispatch a change event.
  const input = document.querySelector('input[type="file"]')
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  fireEvent.change(input)
}

function makeFile(name, content, type = 'text/plain') {
  return new File([content], name, { type })
}

describe('ChatInput attachments', () => {
  it('blocks send while a text-file read is pending', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} disabled={false} />)

    // Type some text BEFORE the read settles — this is the race codex
    // flagged: in the old code the message would send without the
    // attachment, and the chip would reappear in the cleared composer.
    fireEvent.change(screen.getByPlaceholderText(/type a message/i), {
      target: { value: 'hello' },
    })

    pickFile(makeFile('notes.md', '# heading\n\nbody'))

    // Wait for the placeholder chip to render. While pending, the send
    // button must be disabled, even though the composer has typed text.
    const sendBtn = screen.getByRole('button', { name: '', hidden: true }) // submit
    // Submit button is the one with type=submit; find it more robustly:
    const submitBtn = document.querySelector('button[type="submit"]')
    await waitFor(() => {
      expect(document.querySelector('.fa-spinner')).toBeTruthy()
    })
    expect(submitBtn.disabled).toBe(true)

    // Pressing Enter must also be a no-op while pending.
    fireEvent.keyDown(screen.getByPlaceholderText(/type a message/i), {
      key: 'Enter',
    })
    expect(onSend).not.toHaveBeenCalled()

    // Resolve the read; now send must work and the message must include the
    // file's content.
    act(() => ControllableFileReader.instances[0].resolve('# heading\n\nbody'))

    await waitFor(() => expect(submitBtn.disabled).toBe(false))
    fireEvent.click(submitBtn)
    expect(onSend).toHaveBeenCalledTimes(1)
    const sentMsg = onSend.mock.calls[0][0]
    expect(sentMsg).toContain('hello')
    expect(sentMsg).toContain('Attached file: `notes.md`')
    expect(sentMsg).toContain('# heading')
  })

  it('removes the attachment chip on read error', async () => {
    render(<ChatInput onSend={() => {}} disabled={false} />)
    pickFile(makeFile('broken.txt', 'whatever'))

    await waitFor(() => {
      expect(document.querySelector('.fa-spinner')).toBeTruthy()
    })

    act(() => ControllableFileReader.instances[0].reject())

    await waitFor(() => {
      expect(document.querySelector('.fa-spinner')).toBeFalsy()
      expect(document.querySelector('.fa-file-lines')).toBeFalsy()
    })
  })

  it('uses a longer fence when the attached file contains ``` runs', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} disabled={false} />)

    const content = 'before\n```\ncode block inside\n```\nafter'
    pickFile(makeFile('post.md', content))

    await waitFor(() =>
      expect(ControllableFileReader.instances.length).toBe(1)
    )
    act(() => ControllableFileReader.instances[0].resolve(content))

    const submitBtn = document.querySelector('button[type="submit"]')
    await waitFor(() => expect(submitBtn.disabled).toBe(false))
    fireEvent.click(submitBtn)

    expect(onSend).toHaveBeenCalledTimes(1)
    const sentMsg = onSend.mock.calls[0][0]
    // The wrapping fence must be longer than any backtick run inside the
    // body, otherwise the inner ``` would close it prematurely.
    expect(sentMsg).toMatch(/````markdown\n/)
    expect(sentMsg).toMatch(/\n````\b|\n````$/m)
    // And the inner fence must survive verbatim.
    expect(sentMsg).toContain('```\ncode block inside\n```')
  })
})

describe('pickFence', () => {
  it('returns 3 backticks for content with no fences', () => {
    expect(pickFence('plain text')).toBe('```')
  })
  it('returns 4 backticks when the content has a 3-tick run', () => {
    expect(pickFence('```js\nfoo\n```')).toBe('````')
  })
  it('returns 5 backticks when the content has a 4-tick run', () => {
    expect(pickFence('````\nnested\n````')).toBe('`````')
  })
  it('handles isolated single backticks without inflating the fence', () => {
    expect(pickFence('inline `x` and `y`')).toBe('```')
  })
})
