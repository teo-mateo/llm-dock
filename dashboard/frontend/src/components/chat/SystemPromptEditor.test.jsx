import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import SystemPromptEditor from './SystemPromptEditor'

// vitest globals are off, so RTL auto-cleanup isn't registered.
afterEach(() => cleanup())

function expand() {
  fireEvent.click(screen.getByRole('button', { name: /System Prompt/ }))
}

describe('SystemPromptEditor', () => {
  it('is collapsed by default', () => {
    const { container } = render(<SystemPromptEditor mainPrompt="hello" onSaveMain={vi.fn()} />)
    expect(container.querySelector('textarea')).toBeNull()
  })

  it('expands to a single textarea — no critic/sidekick prompt', () => {
    const { container } = render(<SystemPromptEditor mainPrompt="hello" onSaveMain={vi.fn()} />)
    expand()
    expect(container.querySelectorAll('textarea')).toHaveLength(1)
    expect(container.textContent).not.toMatch(/critic/i)
    expect(container.textContent).not.toMatch(/sidekick/i)
  })

  it('is editable — typed text appears in the textarea', () => {
    const { container } = render(<SystemPromptEditor mainPrompt="hello" onSaveMain={vi.fn()} />)
    expand()
    const ta = container.querySelector('textarea')
    expect(ta.value).toBe('hello')
    fireEvent.change(ta, { target: { value: 'hello world' } })
    expect(ta.value).toBe('hello world')
  })

  it('persists on blur when the prompt changed', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { container } = render(<SystemPromptEditor mainPrompt="hello" onSaveMain={onSave} />)
    expand()
    const ta = container.querySelector('textarea')
    fireEvent.change(ta, { target: { value: 'edited prompt' } })
    fireEvent.blur(ta)
    await waitFor(() => expect(onSave).toHaveBeenCalledWith('edited prompt'))
    expect(onSave).toHaveBeenCalledTimes(1)
  })

  it('does not persist on blur when the prompt is unchanged', () => {
    const onSave = vi.fn()
    const { container } = render(<SystemPromptEditor mainPrompt="hello" onSaveMain={onSave} />)
    expand()
    fireEvent.blur(container.querySelector('textarea'))
    expect(onSave).not.toHaveBeenCalled()
  })

  it('shows Unsaved while dirty and clears it after a successful save', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { container } = render(<SystemPromptEditor mainPrompt="hello" onSaveMain={onSave} />)
    expand()
    const ta = container.querySelector('textarea')
    fireEvent.change(ta, { target: { value: 'edited' } })
    expect(container.textContent).toContain('Unsaved')
    fireEvent.blur(ta)
    await waitFor(() => expect(container.textContent).not.toContain('Unsaved'))
  })

  it('keeps Unsaved and surfaces the error when the save fails', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('network down'))
    const { container } = render(<SystemPromptEditor mainPrompt="hello" onSaveMain={onSave} />)
    expand()
    const ta = container.querySelector('textarea')
    fireEvent.change(ta, { target: { value: 'edited' } })
    fireEvent.blur(ta)
    await waitFor(() => expect(container.textContent).toContain('network down'))
    expect(container.textContent).toContain('Unsaved')
  })

  it('does not re-save an already-saved value on a second blur', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { container } = render(<SystemPromptEditor mainPrompt="hello" onSaveMain={onSave} />)
    expand()
    const ta = container.querySelector('textarea')
    fireEvent.change(ta, { target: { value: 'edited' } })
    fireEvent.blur(ta)
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
    fireEvent.blur(ta)  // nothing changed since the save
    expect(onSave).toHaveBeenCalledTimes(1)
  })
})
