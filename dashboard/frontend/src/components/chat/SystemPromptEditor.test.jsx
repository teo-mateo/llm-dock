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

  it('flush() persists an unsaved (un-blurred) edit and resolves only after it lands', async () => {
    let resolveSave
    const onSave = vi.fn().mockImplementationOnce(() => new Promise((r) => { resolveSave = r }))
    const ref = { current: null }
    const { container } = render(
      <SystemPromptEditor ref={ref} mainPrompt="orig" onSaveMain={onSave} />,
    )
    expand()
    // Edit but do NOT blur — flush() must still persist it.
    fireEvent.change(container.querySelector('textarea'), { target: { value: 'edited' } })

    let flushed = false
    ref.current.flush().then(() => { flushed = true })
    await Promise.resolve()
    expect(onSave).toHaveBeenCalledWith('edited')
    expect(flushed).toBe(false) // still in flight

    resolveSave()
    await waitFor(() => expect(flushed).toBe(true))
  })

  it('flush() resolves immediately when there is nothing to save', async () => {
    const onSave = vi.fn()
    const ref = { current: null }
    render(<SystemPromptEditor ref={ref} mainPrompt="orig" onSaveMain={onSave} />)
    await ref.current.flush()
    expect(onSave).not.toHaveBeenCalled()
  })

  it('persists an edit made while an earlier save is still in flight', async () => {
    // Regression for PR #44 codex iteration 2: a blur during an in-flight
    // save was dropped by the `saving` guard, so the later edit never got
    // persisted. The commit loop must catch it once the first PUT settles.
    let resolveFirst
    const onSave = vi.fn()
      .mockImplementationOnce(() => new Promise((r) => { resolveFirst = r }))
      .mockResolvedValueOnce(undefined)
    const { container } = render(<SystemPromptEditor mainPrompt="orig" onSaveMain={onSave} />)
    expand()
    const ta = container.querySelector('textarea')

    // Edit to A and blur — starts the (deferred) save of A.
    fireEvent.change(ta, { target: { value: 'A' } })
    fireEvent.blur(ta)
    expect(onSave).toHaveBeenNthCalledWith(1, 'A')

    // Edit to B while A's save is in flight; this blur is dropped by the
    // `saving` guard and must NOT trigger its own save yet.
    fireEvent.change(ta, { target: { value: 'B' } })
    fireEvent.blur(ta)
    expect(onSave).toHaveBeenCalledTimes(1)

    // Once A's save settles, the loop must persist the latest value (B).
    resolveFirst()
    await waitFor(() => expect(onSave).toHaveBeenNthCalledWith(2, 'B'))
    await waitFor(() => expect(container.textContent).not.toContain('Unsaved'))
  })
})
