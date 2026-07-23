import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'

const mockCreate = vi.fn()
const mockUpdate = vi.fn()
const mockRemove = vi.fn()
const mockReorder = vi.fn()
const mockRefetch = vi.fn()

let hookState

vi.mock('../../hooks/useChatPrompts', () => ({
  default: () => hookState,
}))

import PromptsEditor from './PromptsEditor'

const PROMPTS = [
  { id: 'p-3', name: 'Third', content: 'You are a terse expert.', sort_order: 2 },
  { id: 'p-1', name: 'First', content: 'You are a helpful assistant.', sort_order: 0 },
  { id: 'p-2', name: 'Second', content: 'You are a coding expert.', sort_order: 1 },
]

beforeEach(() => {
  mockCreate.mockReset()
  mockUpdate.mockReset()
  mockRemove.mockReset()
  mockReorder.mockReset()
  mockRefetch.mockReset()
  hookState = {
    prompts: [...PROMPTS],
    loading: false,
    error: null,
    refetch: mockRefetch,
    create: mockCreate,
    update: mockUpdate,
    remove: mockRemove,
    reorder: mockReorder,
  }
})

afterEach(() => cleanup())

describe('PromptsEditor', () => {
  it('renders the heading', () => {
    render(<PromptsEditor />)
    expect(screen.getByText('Managed System Prompts')).toBeTruthy()
  })

  it('shows a loading state while loading', () => {
    hookState = { ...hookState, loading: true, prompts: [] }
    render(<PromptsEditor />)
    expect(screen.getByText('Loading prompts...')).toBeTruthy()
    expect(screen.queryByText('Add Prompt')).toBeNull()
  })

  it('shows an error state when loading fails', () => {
    hookState = { ...hookState, loading: false, error: 'Failed to load' }
    render(<PromptsEditor />)
    expect(screen.getByText('Failed to load')).toBeTruthy()
  })

  it('shows an empty state when there are no prompts', () => {
    hookState = { ...hookState, prompts: [] }
    render(<PromptsEditor />)
    expect(screen.getByText('No managed prompts yet. Add one to get started.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Add Prompt' })).toBeTruthy()
  })

  it('renders prompts sorted by sort_order', () => {
    render(<PromptsEditor />)
    const names = screen.getAllByText(/^(First|Second|Third)$/)
    expect(names[0].textContent).toBe('First')
    expect(names[1].textContent).toBe('Second')
    expect(names[2].textContent).toBe('Third')
  })

  it('shows the Add Prompt button when not adding or editing', () => {
    render(<PromptsEditor />)
    expect(screen.getByRole('button', { name: 'Add Prompt' })).toBeTruthy()
  })

  it('hides the Add Prompt button while adding', () => {
    render(<PromptsEditor />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Prompt' }))
    expect(screen.queryByRole('button', { name: 'Add Prompt' })).toBeNull()
  })

  it('shows the add form when Add Prompt is clicked', () => {
    render(<PromptsEditor />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Prompt' }))
    expect(screen.getByPlaceholderText('Prompt name')).toBeTruthy()
    expect(screen.getByPlaceholderText('Prompt content')).toBeTruthy()
  })

  it('hides the add form when Cancel is clicked', () => {
    render(<PromptsEditor />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Prompt' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByPlaceholderText('Prompt name')).toBeNull()
    expect(screen.getByRole('button', { name: 'Add Prompt' })).toBeTruthy()
  })

  it('disables Save when name is empty', () => {
    render(<PromptsEditor />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Prompt' }))
    fireEvent.change(screen.getByPlaceholderText('Prompt content'), {
      target: { value: 'some content' },
    })
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('disables Save when content is empty', () => {
    render(<PromptsEditor />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Prompt' }))
    fireEvent.change(screen.getByPlaceholderText('Prompt name'), {
      target: { value: 'My Prompt' },
    })
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('shows validation warnings when fields are empty', () => {
    render(<PromptsEditor />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Prompt' }))
    expect(screen.getByText('Name is required.')).toBeTruthy()
    expect(screen.getByText('Content is required.')).toBeTruthy()
  })

  it('calls create with name and content on Save', async () => {
    mockCreate.mockResolvedValue({ id: 'new-1', name: 'New', content: 'content', sort_order: 3 })
    render(<PromptsEditor />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Prompt' }))
    fireEvent.change(screen.getByPlaceholderText('Prompt name'), { target: { value: 'New Prompt' } })
    fireEvent.change(screen.getByPlaceholderText('Prompt content'), { target: { value: 'New content' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(mockCreate).toHaveBeenCalledWith('New Prompt', 'New content'))
  })

  it('closes the add form and shows feedback after a successful create', async () => {
    mockCreate.mockResolvedValue({ id: 'new-1', name: 'New', content: 'content', sort_order: 3 })
    render(<PromptsEditor />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Prompt' }))
    fireEvent.change(screen.getByPlaceholderText('Prompt name'), { target: { value: 'New Prompt' } })
    fireEvent.change(screen.getByPlaceholderText('Prompt content'), { target: { value: 'New content' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(screen.getByText('Prompt created.')).toBeTruthy())
    expect(screen.queryByPlaceholderText('Prompt name')).toBeNull()
  })

  it('shows a feedback error when create fails', async () => {
    mockCreate.mockRejectedValue(new Error('Network error'))
    render(<PromptsEditor />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Prompt' }))
    fireEvent.change(screen.getByPlaceholderText('Prompt name'), { target: { value: 'New Prompt' } })
    fireEvent.change(screen.getByPlaceholderText('Prompt content'), { target: { value: 'New content' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(screen.getByText('Network error')).toBeTruthy())
  })

  it('shows the edit form pre-filled when Edit is clicked', () => {
    render(<PromptsEditor />)
    const editButtons = screen.getAllByTitle('Edit')
    fireEvent.click(editButtons[0])
    expect(screen.getByDisplayValue('First')).toBeTruthy()
    expect(screen.getByDisplayValue('You are a helpful assistant.')).toBeTruthy()
  })

  it('hides the add button while editing', () => {
    render(<PromptsEditor />)
    fireEvent.click(screen.getAllByTitle('Edit')[0])
    expect(screen.queryByRole('button', { name: 'Add Prompt' })).toBeNull()
  })

  it('calls update with id, name, and content on Save in edit mode', async () => {
    mockUpdate.mockResolvedValue({ id: 'p-1', name: 'Updated', content: 'Updated content', sort_order: 0 })
    render(<PromptsEditor />)
    fireEvent.click(screen.getAllByTitle('Edit')[0])
    fireEvent.change(screen.getByDisplayValue('First'), { target: { value: 'Updated Name' } })
    fireEvent.change(screen.getByDisplayValue('You are a helpful assistant.'), { target: { value: 'Updated content' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith('p-1', 'Updated Name', 'Updated content'))
  })

  it('closes the edit form and shows feedback after a successful update', async () => {
    mockUpdate.mockResolvedValue({ id: 'p-1', name: 'Updated', content: 'Updated content', sort_order: 0 })
    render(<PromptsEditor />)
    fireEvent.click(screen.getAllByTitle('Edit')[0])
    fireEvent.change(screen.getByDisplayValue('First'), { target: { value: 'Updated Name' } })
    fireEvent.change(screen.getByDisplayValue('You are a helpful assistant.'), { target: { value: 'Updated content' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(screen.getByText('Prompt saved.')).toBeTruthy())
  })

  it('shows a feedback error when update fails', async () => {
    mockUpdate.mockRejectedValue(new Error('Update failed'))
    render(<PromptsEditor />)
    fireEvent.click(screen.getAllByTitle('Edit')[0])
    fireEvent.change(screen.getByDisplayValue('First'), { target: { value: 'Updated' } })
    fireEvent.change(screen.getByDisplayValue('You are a helpful assistant.'), { target: { value: 'Updated' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(screen.getByText('Update failed')).toBeTruthy())
  })

  it('closes the edit form when Cancel is clicked', () => {
    render(<PromptsEditor />)
    fireEvent.click(screen.getAllByTitle('Edit')[0])
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByDisplayValue('First')).toBeNull()
  })

  it('shows delete confirmation when Delete is clicked', () => {
    render(<PromptsEditor />)
    fireEvent.click(screen.getAllByTitle('Delete')[0])
    expect(screen.getByText('Delete "First"?')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Yes' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'No' })).toBeTruthy()
  })

  it('calls remove when delete is confirmed', async () => {
    mockRemove.mockResolvedValue(undefined)
    render(<PromptsEditor />)
    fireEvent.click(screen.getAllByTitle('Delete')[0])
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }))

    await waitFor(() => expect(mockRemove).toHaveBeenCalledWith('p-1'))
  })

  it('shows feedback after a successful delete', async () => {
    mockRemove.mockResolvedValue(undefined)
    render(<PromptsEditor />)
    fireEvent.click(screen.getAllByTitle('Delete')[0])
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }))

    await waitFor(() => expect(screen.getByText('Prompt deleted.')).toBeTruthy())
  })

  it('shows a feedback error when delete fails', async () => {
    mockRemove.mockRejectedValue(new Error('Delete failed'))
    render(<PromptsEditor />)
    fireEvent.click(screen.getAllByTitle('Delete')[0])
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }))

    await waitFor(() => expect(screen.getByText('Delete failed')).toBeTruthy())
  })

  it('cancels delete when No is clicked', () => {
    render(<PromptsEditor />)
    fireEvent.click(screen.getAllByTitle('Delete')[0])
    fireEvent.click(screen.getByRole('button', { name: 'No' }))
    expect(screen.queryByText('Delete "First"?')).toBeNull()
    expect(mockRemove).not.toHaveBeenCalled()
  })

  it('calls reorder with swapped ids when Move Up is clicked', async () => {
    mockReorder.mockResolvedValue(undefined)
    render(<PromptsEditor />)
    const upButtons = screen.getAllByTitle('Move up')
    fireEvent.click(upButtons[1])

    await waitFor(() => {
      expect(mockReorder).toHaveBeenCalledWith(['p-2', 'p-1', 'p-3'])
    })
  })

  it('calls reorder with swapped ids when Move Down is clicked', async () => {
    mockReorder.mockResolvedValue(undefined)
    render(<PromptsEditor />)
    const downButtons = screen.getAllByTitle('Move down')
    fireEvent.click(downButtons[0])

    await waitFor(() => {
      expect(mockReorder).toHaveBeenCalledWith(['p-2', 'p-1', 'p-3'])
    })
  })

  it('disables Move Up for the first item', () => {
    render(<PromptsEditor />)
    const upButtons = screen.getAllByTitle('Move up')
    expect(upButtons[0]).toBeDisabled()
    expect(upButtons[1]).not.toBeDisabled()
  })

  it('disables Move Down for the last item', () => {
    render(<PromptsEditor />)
    const downButtons = screen.getAllByTitle('Move down')
    expect(downButtons[2]).toBeDisabled()
    expect(downButtons[1]).not.toBeDisabled()
  })

  it('shows a truncated content preview by default', () => {
    const longPrompts = [
      { id: 'p-1', name: 'Long', content: 'X'.repeat(200), sort_order: 0 },
    ]
    hookState = { ...hookState, prompts: longPrompts }
    render(<PromptsEditor />)
    const preview = screen.getByText(/XXX/)
    expect(preview.textContent.length).toBeLessThan(200)
  })

  it('expands full content when More is clicked', () => {
    const longContent = 'X'.repeat(200)
    const longPrompts = [
      { id: 'p-1', name: 'Long', content: longContent, sort_order: 0 },
    ]
    hookState = { ...hookState, prompts: longPrompts }
    render(<PromptsEditor />)
    fireEvent.click(screen.getByText('More'))
    expect(screen.getByText(longContent)).toBeTruthy()
  })

  it('collapses back to preview when Less is clicked', () => {
    const longContent = 'X'.repeat(200)
    const longPrompts = [
      { id: 'p-1', name: 'Long', content: longContent, sort_order: 0 },
    ]
    hookState = { ...hookState, prompts: longPrompts }
    render(<PromptsEditor />)
    fireEvent.click(screen.getByText('More'))
    fireEvent.click(screen.getByText('Less'))
    expect(screen.queryByText(longContent)).toBeNull()
  })

  it('does not show More/Less for short content', () => {
    render(<PromptsEditor />)
    expect(screen.queryByText('More')).toBeNull()
    expect(screen.queryByText('Less')).toBeNull()
  })

  it('hides the list and shows the add form when adding', () => {
    render(<PromptsEditor />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Prompt' }))
    expect(screen.queryByText('First')).toBeNull()
    expect(screen.queryByText('Second')).toBeNull()
    expect(screen.queryByText('Third')).toBeNull()
  })
})
