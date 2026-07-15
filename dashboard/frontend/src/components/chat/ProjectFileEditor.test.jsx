import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import ProjectFileEditor from './ProjectFileEditor'

const { mockGet, mockSave } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockSave: vi.fn(),
}))
vi.mock('../../services/chat', () => ({
  getProjectFileContent: (...a) => mockGet(...a),
  saveProjectFileContent: (...a) => mockSave(...a),
}))

beforeEach(() => {
  mockGet.mockReset().mockResolvedValue({ path: 'notes.md', content: 'hello', revision: 'r100' })
  mockSave.mockReset().mockResolvedValue({ path: 'notes.md', revision: 'r101' })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

async function renderEditor(props = {}) {
  const onClose = vi.fn()
  const onSaved = vi.fn()
  render(
    <ProjectFileEditor projectId="p1" path="notes.md" onClose={onClose} onSaved={onSaved} {...props} />
  )
  if (!props.isNew) {
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('p1', 'notes.md'))
    await screen.findByTestId('editor-textarea')
  }
  return { onClose, onSaved }
}

describe('ProjectFileEditor', () => {
  it('loads content and saves with the loaded revision as conflict base', async () => {
    const { onSaved } = await renderEditor()
    const ta = screen.getByTestId('editor-textarea')
    expect(ta.value).toBe('hello')
    expect(screen.queryByTestId('dirty-indicator')).toBeNull()

    fireEvent.change(ta, { target: { value: 'hello world' } })
    expect(screen.getByTestId('dirty-indicator')).toBeTruthy()

    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith('p1', 'notes.md', 'hello world', 'r100'))
    await waitFor(() => expect(screen.queryByTestId('dirty-indicator')).toBeNull())
    expect(onSaved).toHaveBeenCalled()
  })

  it('Ctrl+S saves when dirty', async () => {
    await renderEditor()
    const ta = screen.getByTestId('editor-textarea')
    fireEvent.change(ta, { target: { value: 'x' } })
    fireEvent.keyDown(ta, { key: 's', ctrlKey: true })
    await waitFor(() => expect(mockSave).toHaveBeenCalled())
  })

  it('save button is disabled while clean', async () => {
    await renderEditor()
    expect(screen.getByText('Save').disabled).toBe(true)
  })

  it('a 409 shows the conflict bar; Overwrite anyway retries without a base', async () => {
    mockSave
      .mockRejectedValueOnce(new Error('file changed on disk since it was loaded'))
      .mockResolvedValueOnce({ path: 'notes.md', revision: 'r102' })
    await renderEditor()
    fireEvent.change(screen.getByTestId('editor-textarea'), { target: { value: 'mine' } })
    fireEvent.click(screen.getByText('Save'))
    await screen.findByText(/changed on disk/)

    fireEvent.click(screen.getByText('Overwrite anyway'))
    await waitFor(() => expect(mockSave).toHaveBeenLastCalledWith('p1', 'notes.md', 'mine', null))
    await waitFor(() => expect(screen.queryByText(/changed on disk/)).toBeNull())
  })

  it('conflict Reload discards local edits and refetches', async () => {
    mockSave.mockRejectedValueOnce(new Error('file changed on disk since it was loaded'))
    await renderEditor()
    fireEvent.change(screen.getByTestId('editor-textarea'), { target: { value: 'mine' } })
    fireEvent.click(screen.getByText('Save'))
    await screen.findByText(/changed on disk/)

    mockGet.mockResolvedValue({ path: 'notes.md', content: 'theirs', revision: 'r200' })
    fireEvent.click(screen.getByText('Reload (discard my changes)'))
    await waitFor(() => expect(screen.getByTestId('editor-textarea').value).toBe('theirs'))
    expect(screen.queryByTestId('dirty-indicator')).toBeNull()
  })

  it('closing with unsaved changes asks for confirmation', async () => {
    const { onClose } = await renderEditor()
    fireEvent.change(screen.getByTestId('editor-textarea'), { target: { value: 'x' } })
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    fireEvent.click(screen.getByLabelText('Close editor'))
    expect(onClose).not.toHaveBeenCalled()
    window.confirm.mockReturnValue(true)
    fireEvent.click(screen.getByLabelText('Close editor'))
    expect(onClose).toHaveBeenCalled()
  })

  it('a new file starts empty and dirty, saving without a conflict base', async () => {
    const { onSaved } = await renderEditor({ isNew: true })
    expect(mockGet).not.toHaveBeenCalled()
    const ta = screen.getByTestId('editor-textarea')
    expect(ta.value).toBe('')
    expect(screen.getByTestId('dirty-indicator')).toBeTruthy()

    fireEvent.change(ta, { target: { value: 'fresh' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith('p1', 'notes.md', 'fresh', null))
    expect(onSaved).toHaveBeenCalled()
  })

  it('shows a load error for binary files', async () => {
    mockGet.mockRejectedValue(new Error('not a text file'))
    render(<ProjectFileEditor projectId="p1" path="img.png" onClose={() => {}} />)
    expect(await screen.findByText('not a text file')).toBeTruthy()
  })
})
