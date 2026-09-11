import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react'
import ChatInput from './ChatInput'
import { pickFence } from '../../utils/fence'

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

describe('ChatInput — trailing control', () => {
  it('renders it inside the text field, at its right edge', () => {
    const marker = <span data-testid="slot">x</span>
    const { getByTestId } = render(<ChatInput onSend={() => {}} trailing={marker} />)
    const field = document.querySelector('textarea')
    const slot = getByTestId('slot')
    // Same wrapper, so the control sits within the field's border rather than
    // joining the attach/send row.
    expect(field.parentElement).toBe(slot.parentElement.parentElement)
    expect(slot.parentElement.className).toContain('absolute')
    expect(slot.parentElement.className).toContain('right-2')
  })

  it('reserves textarea padding only when something is docked there', () => {
    const marker = <span data-testid="slot" />
    const withSlot = render(<ChatInput onSend={() => {}} trailing={marker} />)
    expect(document.querySelector('textarea').className).toContain('pr-28')
    withSlot.unmount()
    render(<ChatInput onSend={() => {}} />)
    const field = document.querySelector('textarea')
    expect(field.className).toContain('px-4')
    expect(field.className).not.toContain('pr-28')
  })

  it('renders nothing extra when no control is passed', () => {
    const { container } = render(<ChatInput onSend={() => {}} />)
    expect(container.querySelectorAll('textarea').length).toBe(1)
    expect(document.querySelector('textarea').parentElement.children).toHaveLength(1)
  })

  it('keeps typing and sending intact around it', () => {
    const onSend = vi.fn()
    const marker = <span data-testid="slot" />
    render(<ChatInput onSend={onSend} trailing={marker} />)
    fireEvent.change(document.querySelector('textarea'), { target: { value: 'hello' } })
    fireEvent.keyDown(document.querySelector('textarea'), { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('hello', undefined)
  })
})
