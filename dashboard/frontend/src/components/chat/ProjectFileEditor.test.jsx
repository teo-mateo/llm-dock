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

// The real API attaches a stable `code` to conflict errors (see api.js);
// the editor branches on it, so mocked rejections must carry it too.
const apiError = (msg, code) => Object.assign(new Error(msg), { code })

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
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith('p1', 'notes.md', 'hello world', 'r100', false))
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
      .mockRejectedValueOnce(apiError('file changed on disk since it was loaded', 'revision_conflict'))
      .mockResolvedValueOnce({ path: 'notes.md', revision: 'r102' })
    await renderEditor()
    fireEvent.change(screen.getByTestId('editor-textarea'), { target: { value: 'mine' } })
    fireEvent.click(screen.getByText('Save'))
    await screen.findByText(/changed on disk/)

    fireEvent.click(screen.getByText('Overwrite anyway'))
    await waitFor(() => expect(mockSave).toHaveBeenLastCalledWith('p1', 'notes.md', 'mine', null, false))
    await waitFor(() => expect(screen.queryByText(/changed on disk/)).toBeNull())
  })

  it('conflict Reload discards local edits and refetches', async () => {
    mockSave.mockRejectedValueOnce(apiError('file changed on disk since it was loaded', 'revision_conflict'))
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
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith('p1', 'notes.md', 'fresh', null, true))
    expect(onSaved).toHaveBeenCalled()
  })

  it('typing during an in-flight save keeps the editor dirty (regression: codex 2.1)', async () => {
    let resolveSave
    mockSave.mockImplementation(() => new Promise(res => { resolveSave = res }))
    await renderEditor()
    const ta = screen.getByTestId('editor-textarea')
    fireEvent.change(ta, { target: { value: 'content A' } })
    fireEvent.click(screen.getByText('Save'))                 // save A, pending
    fireEvent.change(ta, { target: { value: 'content B' } })  // keep typing

    resolveSave({ path: 'notes.md', revision: 'rA' })
    await waitFor(() => expect(screen.getByText('Save').disabled).toBe(false))
    // B is newer than the saved snapshot: still dirty, still saveable.
    expect(screen.getByTestId('dirty-indicator')).toBeTruthy()
    mockSave.mockResolvedValue({ path: 'notes.md', revision: 'rB' })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(mockSave).toHaveBeenLastCalledWith('p1', 'notes.md', 'content B', 'rA', false))
    await waitFor(() => expect(screen.queryByTestId('dirty-indicator')).toBeNull())
  })

  it('new-file saves carry the create-only precondition (regression: codex 2.2)', async () => {
    await renderEditor({ isNew: true })
    fireEvent.change(screen.getByTestId('editor-textarea'), { target: { value: 'fresh' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith('p1', 'notes.md', 'fresh', null, true))
  })

  it('a create-only 409 shows the already-exists conflict; Reload opens the on-disk file and drops create mode', async () => {
    mockSave.mockRejectedValueOnce(apiError('file already exists', 'already_exists'))
    await renderEditor({ isNew: true })
    fireEvent.change(screen.getByTestId('editor-textarea'), { target: { value: 'mine' } })
    fireEvent.click(screen.getByText('Save'))
    await screen.findByText(/already exists/)

    mockGet.mockResolvedValue({ path: 'notes.md', content: 'on disk', revision: 'rd' })
    fireEvent.click(screen.getByText('Reload (discard my changes)'))
    await waitFor(() => expect(screen.getByTestId('editor-textarea').value).toBe('on disk'))
    // Editing and saving again is a normal guarded save now, not create-only.
    fireEvent.change(screen.getByTestId('editor-textarea'), { target: { value: 'edited' } })
    mockSave.mockResolvedValue({ path: 'notes.md', revision: 're' })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(mockSave).toHaveBeenLastCalledWith('p1', 'notes.md', 'edited', 'rd', false))
  })

  it('a create-only 409 Overwrite anyway forces a plain save', async () => {
    mockSave
      .mockRejectedValueOnce(apiError('file already exists', 'already_exists'))
      .mockResolvedValueOnce({ path: 'notes.md', revision: 'rf' })
    await renderEditor({ isNew: true })
    fireEvent.change(screen.getByTestId('editor-textarea'), { target: { value: 'mine' } })
    fireEvent.click(screen.getByText('Save'))
    await screen.findByText(/already exists/)
    fireEvent.click(screen.getByText('Overwrite anyway'))
    await waitFor(() => expect(mockSave).toHaveBeenLastCalledWith('p1', 'notes.md', 'mine', null, false))
  })

  it('arms a beforeunload guard while dirty and disarms after save', async () => {
    await renderEditor()
    const fire = () => {
      const evt = new Event('beforeunload', { cancelable: true })
      window.dispatchEvent(evt)
      return evt.defaultPrevented
    }
    expect(fire()).toBe(false)                                 // clean: no guard
    fireEvent.change(screen.getByTestId('editor-textarea'), { target: { value: 'x' } })
    expect(fire()).toBe(true)                                  // dirty: guarded
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(screen.queryByTestId('dirty-indicator')).toBeNull())
    expect(fire()).toBe(false)                                 // clean again
  })

  it('reports dirty transitions via onDirtyChange and resets on unmount', async () => {
    const onDirtyChange = vi.fn()
    const { unmount } = render(
      <ProjectFileEditor projectId="p1" path="notes.md" onClose={() => {}} onDirtyChange={onDirtyChange} />
    )
    await screen.findByTestId('editor-textarea')
    fireEvent.change(screen.getByTestId('editor-textarea'), { target: { value: 'x' } })
    expect(onDirtyChange).toHaveBeenLastCalledWith(true)
    unmount()
    expect(onDirtyChange).toHaveBeenLastCalledWith(false)
  })

  it('a failed load shows the error WITHOUT a writable textarea (regression: codex 6.1)', async () => {
    // A blank editable buffer over an unread file would save as an
    // unconditional overwrite of content the user never saw.
    mockGet.mockRejectedValue(new Error('not a text file'))
    render(<ProjectFileEditor projectId="p1" path="img.png" onClose={() => {}} />)
    expect(await screen.findByText('not a text file')).toBeTruthy()
    expect(screen.queryByTestId('editor-textarea')).toBeNull()
    expect(screen.getByText('Save').disabled).toBe(true)
  })

  it('Retry after a transient load failure opens the editor normally', async () => {
    mockGet
      .mockRejectedValueOnce(new Error('HTTP 500'))
      .mockResolvedValueOnce({ path: 'notes.md', content: 'recovered', revision: 'rr' })
    render(<ProjectFileEditor projectId="p1" path="notes.md" onClose={() => {}} />)
    await screen.findByText('HTTP 500')
    fireEvent.click(screen.getByLabelText('Retry loading file'))
    await waitFor(() => expect(screen.getByTestId('editor-textarea').value).toBe('recovered'))
  })
})
