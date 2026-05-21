import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'

// The component drives everything through the useMainSystemPrompt hook;
// mock it so each test controls the data / save / reset behavior.
const mockSave = vi.fn()
const mockReset = vi.fn()
let hookState

vi.mock('../../hooks/useMainSystemPrompt', () => ({
  default: () => hookState,
}))

import DefaultPromptEditor from './DefaultPromptEditor'

const BUILTIN = 'You are a helpful assistant.'

beforeEach(() => {
  mockSave.mockReset()
  mockReset.mockReset()
  hookState = {
    data: { current: BUILTIN, builtin: BUILTIN, customized: false },
    loading: false,
    error: null,
    refresh: vi.fn(),
    save: mockSave,
    reset: mockReset,
  }
})

afterEach(() => {
  // vitest globals are off, so RTL's auto-cleanup isn't registered —
  // unmount explicitly or screen queries see prior renders' DOM.
  cleanup()
})

function getTextarea(container) {
  return container.querySelector('textarea')
}

describe('DefaultPromptEditor', () => {
  it('shows a loading state with no textarea while loading', () => {
    hookState = { ...hookState, data: null, loading: true }
    const { container } = render(<DefaultPromptEditor />)
    expect(container.textContent).toContain('Loading…')
    expect(getTextarea(container)).toBeNull()
  })

  it('populates the textarea with the current prompt once loaded', () => {
    const { container } = render(<DefaultPromptEditor />)
    expect(getTextarea(container).value).toBe(BUILTIN)
  })

  it('hides the modified badge when not customized', () => {
    const { container } = render(<DefaultPromptEditor />)
    expect(container.textContent).not.toContain('Modified from built-in')
  })

  it('shows the modified badge when customized', () => {
    hookState.data = { current: 'custom', builtin: BUILTIN, customized: true }
    const { container } = render(<DefaultPromptEditor />)
    expect(container.textContent).toContain('Modified from built-in')
  })

  it('Save is disabled until the prompt is edited', () => {
    const { container } = render(<DefaultPromptEditor />)
    const save = screen.getByRole('button', { name: 'Save' })
    expect(save).toBeDisabled()
    fireEvent.change(getTextarea(container), { target: { value: 'edited prompt' } })
    expect(save).toBeEnabled()
  })

  it('marks the editor dirty when edited', () => {
    const { container } = render(<DefaultPromptEditor />)
    fireEvent.change(getTextarea(container), { target: { value: 'edited' } })
    expect(container.textContent).toContain('Unsaved')
  })

  it('Save calls the hook with the edited content and clears dirty', async () => {
    mockSave.mockResolvedValue({ current: 'edited prompt', builtin: BUILTIN, customized: true })
    const { container } = render(<DefaultPromptEditor />)
    fireEvent.change(getTextarea(container), { target: { value: 'edited prompt' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(mockSave).toHaveBeenCalledWith('edited prompt'))
    await waitFor(() => expect(container.textContent).toContain('Saved'))
    expect(container.textContent).not.toContain('Unsaved')
  })

  it('Save is blocked and a warning shown when the prompt is empty', () => {
    const { container } = render(<DefaultPromptEditor />)
    fireEvent.change(getTextarea(container), { target: { value: '   ' } })
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    expect(container.textContent).toContain('Prompt cannot be empty.')
  })

  it('surfaces a save error from the hook', async () => {
    mockSave.mockRejectedValue(new Error('content must not be empty'))
    const { container } = render(<DefaultPromptEditor />)
    fireEvent.change(getTextarea(container), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(container.textContent).toContain('content must not be empty'))
  })

  it('Discard reverts edits back to the loaded value', () => {
    const { container } = render(<DefaultPromptEditor />)
    fireEvent.change(getTextarea(container), { target: { value: 'edited' } })
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }))
    expect(getTextarea(container).value).toBe(BUILTIN)
    expect(container.textContent).not.toContain('Unsaved')
  })

  it('Reset to built-in is disabled when already on the built-in', () => {
    const { container } = render(<DefaultPromptEditor />)
    expect(screen.getByRole('button', { name: 'Reset to built-in' })).toBeDisabled()
    expect(container).toBeTruthy()
  })

  it('Reset flow: confirm step then hook call', async () => {
    hookState.data = { current: 'custom prompt', builtin: BUILTIN, customized: true }
    mockReset.mockResolvedValue({ current: BUILTIN, builtin: BUILTIN, customized: false })
    const { container } = render(<DefaultPromptEditor />)

    // First click reveals an inline confirm — it does not call the hook.
    fireEvent.click(screen.getByRole('button', { name: 'Reset to built-in' }))
    expect(mockReset).not.toHaveBeenCalled()
    expect(container.textContent).toContain('Reset to built-in?')

    fireEvent.click(screen.getByRole('button', { name: 'Confirm reset' }))
    await waitFor(() => expect(mockReset).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(getTextarea(container).value).toBe(BUILTIN))
    expect(container.textContent).toContain('Reset to built-in')
  })

  it('Reset can be cancelled at the confirm step', () => {
    hookState.data = { current: 'custom prompt', builtin: BUILTIN, customized: true }
    const { container } = render(<DefaultPromptEditor />)
    fireEvent.click(screen.getByRole('button', { name: 'Reset to built-in' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(container.textContent).not.toContain('Reset to built-in?')
    expect(mockReset).not.toHaveBeenCalled()
  })

  it('surfaces a load error from the hook', () => {
    hookState = { ...hookState, data: null, loading: false, error: 'Failed to load default prompt' }
    const { container } = render(<DefaultPromptEditor />)
    expect(container.textContent).toContain('Failed to load default prompt')
  })
})
