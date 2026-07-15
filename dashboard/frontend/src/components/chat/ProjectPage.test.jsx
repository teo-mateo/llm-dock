import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup, within } from '@testing-library/react'
import ProjectPage from './ProjectPage'

const { mockTree, mockUpload, mockMkdir, mockMove, mockCopy, mockDelete, mockGetContent, mockSaveContent } = vi.hoisted(() => ({
  mockTree: vi.fn(),
  mockUpload: vi.fn(),
  mockMkdir: vi.fn(),
  mockMove: vi.fn(),
  mockCopy: vi.fn(),
  mockDelete: vi.fn(),
  mockGetContent: vi.fn(),
  mockSaveContent: vi.fn(),
}))
vi.mock('../../services/chat', () => ({
  getProjectFilesTree: (...a) => mockTree(...a),
  uploadProjectFile: (...a) => mockUpload(...a),
  mkdirProjectPath: (...a) => mockMkdir(...a),
  moveProjectPath: (...a) => mockMove(...a),
  copyProjectPath: (...a) => mockCopy(...a),
  deleteProjectPath: (...a) => mockDelete(...a),
  downloadProjectFile: vi.fn(),
  getProjectFileContent: (...a) => mockGetContent(...a),
  saveProjectFileContent: (...a) => mockSaveContent(...a),
}))

const project = { id: 'p1', name: 'Research', description: 'notes & data' }

const TREE = [
  { name: 'archive', path: 'archive', type: 'dir', modified_at: 1, children: [] },
  {
    name: 'docs', path: 'docs', type: 'dir', modified_at: 1, children: [
      { name: 'inner', path: 'docs/inner', type: 'dir', modified_at: 1, children: [] },
      { name: 'a.txt', path: 'docs/a.txt', type: 'file', size: 5, modified_at: 1 },
    ],
  },
  { name: 'readme.md', path: 'readme.md', type: 'file', size: 12, modified_at: 1 },
]

beforeEach(() => {
  mockTree.mockReset().mockResolvedValue({ tree: TREE })
  mockUpload.mockReset().mockResolvedValue({})
  mockMkdir.mockReset().mockResolvedValue({})
  mockMove.mockReset().mockResolvedValue({})
  mockCopy.mockReset().mockResolvedValue({})
  mockDelete.mockReset().mockResolvedValue({ ok: true })
  mockGetContent.mockReset().mockResolvedValue({ path: 'readme.md', content: 'doc', revision: 'r1' })
  mockSaveContent.mockReset().mockResolvedValue({ path: 'readme.md', revision: 'r2' })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

async function renderPage() {
  render(<ProjectPage project={project} />)
  await waitFor(() => expect(mockTree).toHaveBeenCalledWith('p1'))
  await screen.findByTestId('file-row-readme.md')
}

// Minimal DataTransfer stand-in — jsdom has no native one.
function makeDataTransfer() {
  return {
    store: {},
    types: [],
    effectAllowed: '',
    dropEffect: '',
    setData(type, val) {
      this.store[type] = val
      if (!this.types.includes(type)) this.types.push(type)
    },
    getData(type) { return this.store[type] || '' },
  }
}

function dragAndDrop(srcEl, dstEl) {
  const dataTransfer = makeDataTransfer()
  fireEvent.dragStart(srcEl, { dataTransfer })
  fireEvent.dragOver(dstEl, { dataTransfer })
  fireEvent.drop(dstEl, { dataTransfer })
}

describe('ProjectPage explorer layout', () => {
  it('renders header, folder tree, and root contents', async () => {
    await renderPage()
    expect(screen.getByRole('heading', { name: 'Research' })).toBeTruthy()
    expect(screen.getByText('notes & data')).toBeTruthy()
    // Tree pane: root node + dirs only.
    expect(screen.getByTestId('tree-node-root')).toBeTruthy()
    expect(screen.getByTestId('tree-node-docs')).toBeTruthy()
    expect(screen.queryByTestId('tree-node-readme.md')).toBeNull()
    // Right pane: root entries; children hidden until docs is selected.
    expect(screen.getByTestId('file-row-docs')).toBeTruthy()
    expect(screen.queryByTestId('file-row-docs/a.txt')).toBeNull()
  })

  it('selecting a folder in the tree shows its contents in the right pane', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('tree-node-docs'))
    expect(screen.getByTestId('file-row-docs/a.txt')).toBeTruthy()
    expect(screen.getByTestId('file-row-docs/inner')).toBeTruthy()
    expect(screen.queryByTestId('file-row-readme.md')).toBeNull()
  })

  it('clicking a folder row in the right pane navigates into it', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('file-row-docs'))
    expect(screen.getByTestId('file-row-docs/a.txt')).toBeTruthy()
  })

  it('breadcrumb navigates back to the root', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('file-row-docs'))
    expect(screen.getByTestId('crumb-docs')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Go to project root'))
    expect(screen.getByTestId('file-row-readme.md')).toBeTruthy()
  })

  it('tree chevron expands subfolders without changing the selection', async () => {
    await renderPage()
    expect(screen.queryByTestId('tree-node-docs/inner')).toBeNull()
    fireEvent.click(screen.getByLabelText('Expand docs'))
    expect(screen.getByTestId('tree-node-docs/inner')).toBeTruthy()
    // Selection unchanged: right pane still shows the root.
    expect(screen.getByTestId('file-row-readme.md')).toBeTruthy()
  })

  it('renders a "Project not found" state without a project', () => {
    render(<ProjectPage project={null} />)
    expect(screen.getByText('Project not found')).toBeTruthy()
    expect(mockTree).not.toHaveBeenCalled()
  })

  it('toolbar actions target the selected folder', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('tree-node-docs'))
    vi.spyOn(window, 'prompt').mockReturnValue('sub')
    fireEvent.click(screen.getByText('New folder'))
    await waitFor(() => expect(mockMkdir).toHaveBeenCalledWith('p1', 'docs/sub'))
  })

  it('creates a folder at root via prompt and refreshes', async () => {
    await renderPage()
    vi.spyOn(window, 'prompt').mockReturnValue('new-folder')
    fireEvent.click(screen.getByText('New folder'))
    await waitFor(() => expect(mockMkdir).toHaveBeenCalledWith('p1', 'new-folder'))
    expect(mockTree).toHaveBeenCalledTimes(2)
  })

  it('uploads picked files into the selected directory', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('tree-node-docs'))
    fireEvent.click(screen.getByText('Upload files'))
    const file = new File(['hello'], 'up.txt', { type: 'text/plain' })
    fireEvent.change(screen.getByTestId('file-input'), { target: { files: [file] } })
    await waitFor(() => expect(mockUpload).toHaveBeenCalledWith('p1', file, { dir: 'docs' }))
  })

  it('offers overwrite when the upload conflicts', async () => {
    mockUpload
      .mockRejectedValueOnce(Object.assign(new Error('file already exists'), { code: 'already_exists' }))
      .mockResolvedValueOnce({})
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await renderPage()
    fireEvent.click(screen.getByText('Upload files'))
    const file = new File(['x'], 'readme.md', { type: 'text/plain' })
    fireEvent.change(screen.getByTestId('file-input'), { target: { files: [file] } })
    await waitFor(() => expect(mockUpload).toHaveBeenCalledTimes(2))
    expect(mockUpload).toHaveBeenLastCalledWith('p1', file, { dir: '', overwrite: true })
  })

  it('renames via prompt with the current path prefilled', async () => {
    await renderPage()
    vi.spyOn(window, 'prompt').mockReturnValue('README.md')
    fireEvent.click(screen.getByLabelText('Rename readme.md'))
    expect(window.prompt).toHaveBeenCalledWith(expect.any(String), 'readme.md')
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('p1', 'readme.md', 'README.md'))
  })

  it('deletes after confirmation', async () => {
    await renderPage()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.click(screen.getByLabelText('Delete readme.md'))
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('p1', 'readme.md'))
  })

  it('does not delete when confirmation is declined', async () => {
    await renderPage()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    fireEvent.click(screen.getByLabelText('Delete readme.md'))
    expect(mockDelete).not.toHaveBeenCalled()
  })

  it('surfaces API errors', async () => {
    await renderPage()
    mockMkdir.mockRejectedValue(new Error('path escapes project root'))
    vi.spyOn(window, 'prompt').mockReturnValue('../evil')
    fireEvent.click(screen.getByText('New folder'))
    expect(await screen.findByText('path escapes project root')).toBeTruthy()
  })

  it('shows the empty state when the project has no files', async () => {
    mockTree.mockResolvedValue({ tree: [] })
    render(<ProjectPage project={project} />)
    expect(await screen.findByText(/No files yet/)).toBeTruthy()
  })

  it('deleting the selected folder falls back to its parent', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('tree-node-docs'))
    expect(screen.getByTestId('file-row-docs/a.txt')).toBeTruthy()
    mockTree.mockResolvedValue({ tree: TREE.filter(n => n.path !== 'docs') }) // docs gone after refresh
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.contextMenu(screen.getByTestId('tree-node-docs'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Delete'))
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('p1', 'docs'))
    // Selection fell back to root, which still has readme.md.
    expect(await screen.findByTestId('file-row-readme.md')).toBeTruthy()
  })
})

describe('ProjectPage context menu', () => {
  it('right-clicking a file offers Open/Download/Cut/Copy/Rename/Delete', async () => {
    await renderPage()
    fireEvent.contextMenu(screen.getByTestId('file-row-readme.md'), { clientX: 5, clientY: 5 })
    const menu = screen.getByTestId('context-menu')
    for (const label of ['Open', 'Download', 'Cut', 'Copy', 'Rename', 'Delete']) {
      expect(within(menu).getByText(label)).toBeTruthy()
    }
  })

  it('closes on Escape without acting', async () => {
    await renderPage()
    fireEvent.contextMenu(screen.getByTestId('file-row-readme.md'), { clientX: 5, clientY: 5 })
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByTestId('context-menu')).toBeNull()
    expect(mockMove).not.toHaveBeenCalled()
    expect(mockDelete).not.toHaveBeenCalled()
  })

  it('cut then paste into a folder moves it and clears the clipboard', async () => {
    await renderPage()
    fireEvent.contextMenu(screen.getByTestId('file-row-readme.md'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Cut'))
    expect(screen.getByTestId('clipboard-chip')).toBeTruthy()
    // Cut source is dimmed while on the clipboard.
    expect(screen.getByTestId('file-row-readme.md').className).toContain('opacity-50')

    fireEvent.contextMenu(screen.getByTestId('file-row-docs'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Paste into'))
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('p1', 'readme.md', 'docs/readme.md'))
    await waitFor(() => expect(screen.queryByTestId('clipboard-chip')).toBeNull())
  })

  it('copy then paste keeps the clipboard and copies with a non-colliding name', async () => {
    await renderPage()
    fireEvent.contextMenu(screen.getByTestId('file-row-readme.md'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Copy'))

    // Paste into the SAME folder → "(copy)" suffix before the extension.
    fireEvent.contextMenu(screen.getByTestId('dir-contents'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Paste'))
    await waitFor(() => expect(mockCopy).toHaveBeenCalledWith('p1', 'readme.md', 'readme (copy).md'))
    // Copy stays on the clipboard for repeated pastes.
    expect(screen.getByTestId('clipboard-chip')).toBeTruthy()
  })

  it('pasting a copied file into a folder without a collision keeps its name', async () => {
    await renderPage()
    fireEvent.contextMenu(screen.getByTestId('file-row-readme.md'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Copy'))
    fireEvent.contextMenu(screen.getByTestId('file-row-docs'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Paste into'))
    await waitFor(() => expect(mockCopy).toHaveBeenCalledWith('p1', 'readme.md', 'docs/readme.md'))
  })

  it('Paste is disabled while the clipboard is empty', async () => {
    await renderPage()
    fireEvent.contextMenu(screen.getByTestId('dir-contents'), { clientX: 5, clientY: 5 })
    expect(within(screen.getByTestId('context-menu')).getByText('Paste').closest('button').disabled).toBe(true)
  })

  it('the clipboard chip can be cleared manually', async () => {
    await renderPage()
    fireEvent.contextMenu(screen.getByTestId('file-row-readme.md'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Cut'))
    fireEvent.click(screen.getByLabelText('Clear clipboard'))
    expect(screen.queryByTestId('clipboard-chip')).toBeNull()
  })

  it('deleting the cut source clears the clipboard', async () => {
    await renderPage()
    fireEvent.contextMenu(screen.getByTestId('file-row-readme.md'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Cut'))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.click(screen.getByLabelText('Delete readme.md'))
    await waitFor(() => expect(mockDelete).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByTestId('clipboard-chip')).toBeNull())
  })

  it('the root tree node menu pastes into the root', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('tree-node-docs')) // selection elsewhere
    fireEvent.contextMenu(screen.getByTestId('file-row-docs/a.txt'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Cut'))
    fireEvent.contextMenu(screen.getByTestId('tree-node-root'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Paste'))
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('p1', 'docs/a.txt', 'a.txt'))
  })

  it('Open on a folder navigates into it', async () => {
    await renderPage()
    fireEvent.contextMenu(screen.getByTestId('file-row-docs'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Open'))
    expect(screen.getByTestId('file-row-docs/a.txt')).toBeTruthy()
  })
})

describe('ProjectPage drag and drop', () => {
  it('dropping a file onto a tree folder moves it there', async () => {
    await renderPage()
    dragAndDrop(screen.getByTestId('file-row-readme.md'), screen.getByTestId('tree-node-docs'))
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('p1', 'readme.md', 'docs/readme.md'))
  })

  it('dropping a file onto a folder row moves it there', async () => {
    await renderPage()
    dragAndDrop(screen.getByTestId('file-row-readme.md'), screen.getByTestId('file-row-docs'))
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('p1', 'readme.md', 'docs/readme.md'))
  })

  it('dropping onto the root tree node moves to the root', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('tree-node-docs'))
    dragAndDrop(screen.getByTestId('file-row-docs/a.txt'), screen.getByTestId('tree-node-root'))
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('p1', 'docs/a.txt', 'a.txt'))
  })

  it('dropping into the item\'s own parent is a no-op', async () => {
    await renderPage()
    dragAndDrop(screen.getByTestId('file-row-readme.md'), screen.getByTestId('tree-node-root'))
    await new Promise(r => setTimeout(r, 0))
    expect(mockMove).not.toHaveBeenCalled()
  })

  it('dropping a folder into its own subtree is rejected client-side', async () => {
    await renderPage()
    fireEvent.click(screen.getByLabelText('Expand docs'))
    dragAndDrop(screen.getByTestId('tree-node-docs'), screen.getByTestId('tree-node-docs/inner'))
    expect(await screen.findByText('cannot move a folder into itself')).toBeTruthy()
    expect(mockMove).not.toHaveBeenCalled()
  })

  it('foreign drags without the internal payload type are ignored', async () => {
    await renderPage()
    const dataTransfer = makeDataTransfer()
    dataTransfer.setData('text/plain', 'whatever')
    fireEvent.dragOver(screen.getByTestId('tree-node-docs'), { dataTransfer })
    fireEvent.drop(screen.getByTestId('tree-node-docs'), { dataTransfer })
    await new Promise(r => setTimeout(r, 0))
    expect(mockMove).not.toHaveBeenCalled()
  })

  it('moving the selected folder keeps the selection on its new path', async () => {
    await renderPage()
    // Select docs/inner, then move it into the root.
    fireEvent.click(screen.getByLabelText('Expand docs'))
    fireEvent.click(screen.getByTestId('tree-node-docs/inner'))
    const movedTree = [
      { name: 'docs', path: 'docs', type: 'dir', modified_at: 1, children: [
        { name: 'a.txt', path: 'docs/a.txt', type: 'file', size: 5, modified_at: 1 },
      ] },
      { name: 'inner', path: 'inner', type: 'dir', modified_at: 1, children: [] },
      { name: 'readme.md', path: 'readme.md', type: 'file', size: 12, modified_at: 1 },
    ]
    mockTree.mockResolvedValue({ tree: movedTree })
    dragAndDrop(screen.getByTestId('tree-node-docs/inner'), screen.getByTestId('tree-node-root'))
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('p1', 'docs/inner', 'inner'))
    // Right pane follows the moved folder (still selected, at its new path).
    await waitFor(() => expect(screen.getByTestId('crumb-inner')).toBeTruthy())
  })
})

describe('ProjectPage open-editor mutation guard (regression: codex 2.1)', () => {
  // The tree stays actionable while the editor is mounted, so mutating
  // the open file's folder must consult the dirty buffer first, and a
  // successful rename/move must carry the editor to the new path.
  async function openDocsFile({ dirty }) {
    await renderPage()
    fireEvent.click(screen.getByTestId('tree-node-docs'))
    fireEvent.click(screen.getByTestId('file-row-docs/a.txt'))
    const ta = await screen.findByTestId('editor-textarea')
    if (dirty) fireEvent.change(ta, { target: { value: 'unsaved work' } })
    return ta
  }

  it('dragging the open file\'s folder with a dirty buffer asks; cancel aborts the move', async () => {
    await openDocsFile({ dirty: true })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    dragAndDrop(screen.getByTestId('tree-node-docs'), screen.getByTestId('tree-node-archive'))
    expect(confirmSpy).toHaveBeenCalled()
    await new Promise(r => setTimeout(r, 0))
    expect(mockMove).not.toHaveBeenCalled()
    expect(screen.getByTestId('editor-textarea').value).toBe('unsaved work')
  })

  it('confirming the discard moves the folder and remaps the editor path', async () => {
    await openDocsFile({ dirty: true })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    dragAndDrop(screen.getByTestId('tree-node-docs'), screen.getByTestId('tree-node-archive'))
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('p1', 'docs', 'archive/docs'))
    // The keyed remount reloads the buffer from the file's new location.
    await waitFor(() => expect(mockGetContent).toHaveBeenLastCalledWith('p1', 'archive/docs/a.txt'))
    expect(screen.getByTestId('file-editor')).toBeTruthy()
  })

  it('renaming the open file\'s folder with a clean buffer remaps without asking', async () => {
    await openDocsFile({ dirty: false })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.spyOn(window, 'prompt').mockReturnValue('notes')
    fireEvent.contextMenu(screen.getByTestId('tree-node-docs'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Rename'))
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('p1', 'docs', 'notes'))
    expect(confirmSpy).not.toHaveBeenCalled()
    await waitFor(() => expect(mockGetContent).toHaveBeenLastCalledWith('p1', 'notes/a.txt'))
  })

  it('deleting the open file\'s folder closes the editor', async () => {
    await openDocsFile({ dirty: true })
    vi.spyOn(window, 'confirm').mockReturnValue(true) // discard + delete confirms
    fireEvent.contextMenu(screen.getByTestId('tree-node-docs'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Delete'))
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('p1', 'docs'))
    await waitFor(() => expect(screen.queryByTestId('file-editor')).toBeNull())
  })

  it('cancelling the discard aborts the delete entirely', async () => {
    await openDocsFile({ dirty: true })
    vi.spyOn(window, 'confirm').mockReturnValueOnce(false) // discard prompt
    fireEvent.contextMenu(screen.getByTestId('tree-node-docs'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Delete'))
    await new Promise(r => setTimeout(r, 0))
    expect(mockDelete).not.toHaveBeenCalled()
    expect(screen.getByTestId('editor-textarea').value).toBe('unsaved work')
  })

  it('cut-pasting the open file itself carries the editor to the destination', async () => {
    await openDocsFile({ dirty: false })
    fireEvent.contextMenu(screen.getByTestId('tree-node-docs'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Cut'))
    fireEvent.contextMenu(screen.getByTestId('tree-node-archive'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Paste into'))
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('p1', 'docs', 'archive/docs'))
    await waitFor(() => expect(mockGetContent).toHaveBeenLastCalledWith('p1', 'archive/docs/a.txt'))
  })
})

describe('ProjectPage rename selection follow (regression: codex 1.1)', () => {
  const renamedTree = [
    { name: 'notes', path: 'notes', type: 'dir', modified_at: 1, children: [
      { name: 'inner', path: 'notes/inner', type: 'dir', modified_at: 1, children: [] },
      { name: 'a.txt', path: 'notes/a.txt', type: 'file', size: 5, modified_at: 1 },
    ] },
    { name: 'readme.md', path: 'readme.md', type: 'file', size: 12, modified_at: 1 },
  ]

  it('renaming an ancestor of the selected folder carries the selection along', async () => {
    await renderPage()
    fireEvent.click(screen.getByLabelText('Expand docs'))
    fireEvent.click(screen.getByTestId('tree-node-docs/inner'))
    mockTree.mockResolvedValue({ tree: renamedTree })
    vi.spyOn(window, 'prompt').mockReturnValue('notes')
    fireEvent.contextMenu(screen.getByTestId('tree-node-docs'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Rename'))
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('p1', 'docs', 'notes'))
    // Selection followed docs/inner → notes/inner instead of falling back.
    await waitFor(() => expect(screen.getByTestId('crumb-notes/inner')).toBeTruthy())
    // And the expansion set followed too: the selected tree row is
    // actually visible, not hidden inside a collapsed "notes" branch
    // (regression: codex 3.1).
    expect(screen.getByTestId('tree-node-notes/inner')).toBeTruthy()
  })

  it('moving an ancestor of the selected folder keeps the selected tree row visible (regression: codex 3.1)', async () => {
    await renderPage()
    fireEvent.click(screen.getByLabelText('Expand docs'))
    fireEvent.click(screen.getByTestId('tree-node-docs/inner'))
    const movedTree = [
      { name: 'archive', path: 'archive', type: 'dir', modified_at: 1, children: [
        { name: 'docs', path: 'archive/docs', type: 'dir', modified_at: 1, children: [
          { name: 'inner', path: 'archive/docs/inner', type: 'dir', modified_at: 1, children: [] },
          { name: 'a.txt', path: 'archive/docs/a.txt', type: 'file', size: 5, modified_at: 1 },
        ] },
      ] },
      { name: 'readme.md', path: 'readme.md', type: 'file', size: 12, modified_at: 1 },
    ]
    mockTree.mockResolvedValue({ tree: movedTree })
    dragAndDrop(screen.getByTestId('tree-node-docs'), screen.getByTestId('tree-node-archive'))
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('p1', 'docs', 'archive/docs'))
    // Selection followed to archive/docs/inner AND its whole branch is
    // expanded, so the selected tree row is on screen.
    await waitFor(() => expect(screen.getByTestId('crumb-archive/docs/inner')).toBeTruthy())
    expect(screen.getByTestId('tree-node-archive/docs/inner')).toBeTruthy()
  })

  it('renaming the selected folder itself follows to the new path', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('tree-node-docs'))
    mockTree.mockResolvedValue({ tree: renamedTree })
    // Slashes are normalized away, matching the backend's path handling.
    vi.spyOn(window, 'prompt').mockReturnValue('/notes/')
    fireEvent.contextMenu(screen.getByTestId('tree-node-docs'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Rename'))
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('p1', 'docs', 'notes'))
    await waitFor(() => expect(screen.getByTestId('crumb-notes')).toBeTruthy())
    expect(screen.getByTestId('file-row-notes/a.txt')).toBeTruthy()
  })

  it('a failed rename leaves the selection where it was', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('tree-node-docs'))
    mockMove.mockRejectedValue(new Error('destination already exists'))
    vi.spyOn(window, 'prompt').mockReturnValue('notes')
    fireEvent.contextMenu(screen.getByTestId('tree-node-docs'), { clientX: 5, clientY: 5 })
    fireEvent.click(within(screen.getByTestId('context-menu')).getByText('Rename'))
    expect(await screen.findByText('destination already exists')).toBeTruthy()
    expect(screen.getByTestId('crumb-docs')).toBeTruthy()
  })
})

describe('ProjectPage editor integration', () => {
  it('clicking a file row opens the editor with its content; closing returns to the listing', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('file-row-readme.md'))
    await waitFor(() => expect(mockGetContent).toHaveBeenCalledWith('p1', 'readme.md'))
    expect(await screen.findByTestId('file-editor')).toBeTruthy()
    expect((await screen.findByTestId('editor-textarea')).value).toBe('doc')

    fireEvent.click(screen.getByLabelText('Close editor'))
    expect(screen.queryByTestId('file-editor')).toBeNull()
    expect(screen.getByTestId('file-row-readme.md')).toBeTruthy()
  })

  it('New file prompts for a name and opens an empty new-file editor', async () => {
    await renderPage()
    vi.spyOn(window, 'prompt').mockReturnValue('fresh.md')
    fireEvent.click(screen.getByText('New file'))
    expect(await screen.findByTestId('file-editor')).toBeTruthy()
    // New file: no content fetch, editor starts dirty for first save.
    expect(mockGetContent).not.toHaveBeenCalled()
    expect(screen.getByTestId('dirty-indicator')).toBeTruthy()
  })

  it('New file with an existing name opens that file instead of a blank editor', async () => {
    await renderPage()
    vi.spyOn(window, 'prompt').mockReturnValue('readme.md')
    fireEvent.click(screen.getByText('New file'))
    await waitFor(() => expect(mockGetContent).toHaveBeenCalledWith('p1', 'readme.md'))
  })

  it('New file in a selected folder creates under that folder', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('tree-node-docs'))
    vi.spyOn(window, 'prompt').mockReturnValue('notes.md')
    fireEvent.click(screen.getByText('New file'))
    const ta = await screen.findByTestId('editor-textarea')
    fireEvent.change(ta, { target: { value: 'x' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(mockSaveContent).toHaveBeenCalledWith('p1', 'docs/notes.md', 'x', null, true))
  })

  it('saving a new file refreshes the tree', async () => {
    await renderPage()
    vi.spyOn(window, 'prompt').mockReturnValue('fresh.md')
    fireEvent.click(screen.getByText('New file'))
    const ta = await screen.findByTestId('editor-textarea')
    fireEvent.change(ta, { target: { value: 'body' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(mockSaveContent).toHaveBeenCalledWith('p1', 'fresh.md', 'body', null, true))
    await waitFor(() => expect(mockTree).toHaveBeenCalledTimes(2))
  })

  it('navigating the tree while the editor is dirty asks first; cancel keeps the editor', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('file-row-readme.md'))
    const ta = await screen.findByTestId('editor-textarea')
    fireEvent.change(ta, { target: { value: 'unsaved work' } })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    fireEvent.click(screen.getByTestId('tree-node-docs'))
    expect(confirmSpy).toHaveBeenCalled()
    expect(screen.getByTestId('editor-textarea').value).toBe('unsaved work')
  })
})

describe('ProjectPage in-page editor replacement guard (regression: codex 5.1)', () => {
  it('New file over a dirty editor asks first; cancel keeps path and text', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('file-row-readme.md'))
    const ta = await screen.findByTestId('editor-textarea')
    fireEvent.change(ta, { target: { value: 'unsaved work' } })

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('b.md')
    fireEvent.click(screen.getByText('New file'))
    expect(confirmSpy).toHaveBeenCalled()
    // Cancelled: same editor, text intact, no name prompt shown.
    expect(promptSpy).not.toHaveBeenCalled()
    expect(screen.getByTestId('editor-textarea').value).toBe('unsaved work')
    expect(screen.getByText('readme.md')).toBeTruthy()
  })

  it('confirming the discard opens the new file editor', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('file-row-readme.md'))
    const ta = await screen.findByTestId('editor-textarea')
    fireEvent.change(ta, { target: { value: 'unsaved work' } })

    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.spyOn(window, 'prompt').mockReturnValue('b.md')
    fireEvent.click(screen.getByText('New file'))
    await waitFor(() => expect(screen.getByTestId('editor-textarea').value).toBe(''))
    expect(screen.getByText('b.md')).toBeTruthy()
  })

  it('New file with a clean editor does not ask', async () => {
    await renderPage()
    fireEvent.click(screen.getByTestId('file-row-readme.md'))
    await screen.findByTestId('editor-textarea')
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.spyOn(window, 'prompt').mockReturnValue('b.md')
    fireEvent.click(screen.getByText('New file'))
    expect(confirmSpy).not.toHaveBeenCalled()
  })
})

describe('ProjectPage new-file first-save race (regression: codex 3.1)', () => {
  it('typing during the first save of a new file survives the isNew flip', async () => {
    // First save of a new file resolves while the user has already typed
    // newer content. onSaved flips isNew on the editor prop — that flip
    // must NOT trigger a reload of the just-saved snapshot, which would
    // clobber the newer text and mark it clean.
    await renderPage()
    vi.spyOn(window, 'prompt').mockReturnValue('fresh.md')
    fireEvent.click(screen.getByText('New file'))
    const ta = await screen.findByTestId('editor-textarea')

    let resolveSave
    mockSaveContent.mockImplementation(() => new Promise(res => { resolveSave = res }))
    fireEvent.change(ta, { target: { value: 'content A' } })
    fireEvent.click(screen.getByText('Save'))                 // create A, pending
    fireEvent.change(ta, { target: { value: 'content B' } })  // keep typing

    mockGetContent.mockResolvedValue({ path: 'fresh.md', content: 'content A', revision: 'rA' })
    resolveSave({ path: 'fresh.md', revision: 'rA' })
    await waitFor(() => expect(screen.getByText('Save').disabled).toBe(false))

    // B intact, still dirty, and no reload happened.
    expect(screen.getByTestId('editor-textarea').value).toBe('content B')
    expect(screen.getByTestId('dirty-indicator')).toBeTruthy()
    expect(mockGetContent).not.toHaveBeenCalled()

    // And B saves as a normal guarded (non-create) write.
    mockSaveContent.mockResolvedValue({ path: 'fresh.md', revision: 'rB' })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(mockSaveContent).toHaveBeenLastCalledWith('p1', 'fresh.md', 'content B', 'rA', false))
  })
})

describe('ProjectPage stale-response guard', () => {
  it('a slow tree response for the previous project never commits after switching', async () => {
    // Project A's fetch is slow; the user switches to B; A resolves LAST.
    // Without the generation guard, A's rows would render under B and row
    // actions (closing over B's id) would target the wrong project.
    let resolveA
    const treeA = [{ name: 'a-only.txt', path: 'a-only.txt', type: 'file', size: 1, modified_at: 1 }]
    const treeB = [{ name: 'b-only.txt', path: 'b-only.txt', type: 'file', size: 1, modified_at: 1 }]
    mockTree.mockImplementation((pid) => {
      if (pid === 'pa') return new Promise(res => { resolveA = res })
      return Promise.resolve({ tree: treeB })
    })

    const { rerender } = render(<ProjectPage project={{ id: 'pa', name: 'A' }} />)
    await waitFor(() => expect(mockTree).toHaveBeenCalledWith('pa'))

    rerender(<ProjectPage project={{ id: 'pb', name: 'B' }} />)
    await screen.findByText('b-only.txt')

    resolveA({ tree: treeA })
    // Give the late resolution a tick to (incorrectly) commit.
    await new Promise(r => setTimeout(r, 0))
    expect(screen.queryByText('a-only.txt')).toBeNull()
    expect(screen.getByText('b-only.txt')).toBeTruthy()
  })
})

describe('ProjectPage stale-mutation guard', () => {
  it('a mutation finishing after a project switch cannot repopulate the page with old rows', async () => {
    // Start a slow mkdir on project A, switch to B, then let A's mutation
    // (and its follow-up refresh) resolve. The follow-up refresh claims a
    // NEWER generation than B's fetch, so the generation guard alone would
    // let it commit — the project-id binding must reject it.
    const treeA = [{ name: 'a-only.txt', path: 'a-only.txt', type: 'file', size: 1, modified_at: 1 }]
    const treeB = [{ name: 'b-only.txt', path: 'b-only.txt', type: 'file', size: 1, modified_at: 1 }]
    mockTree.mockImplementation((pid) =>
      Promise.resolve({ tree: pid === 'pa' ? treeA : treeB }))
    let resolveMkdir
    mockMkdir.mockImplementation(() => new Promise(res => { resolveMkdir = res }))
    vi.spyOn(window, 'prompt').mockReturnValue('slow-dir')

    const { rerender } = render(<ProjectPage project={{ id: 'pa', name: 'A' }} />)
    await screen.findByText('a-only.txt')
    fireEvent.click(screen.getByText('New folder'))         // A's mutation, pending
    await waitFor(() => expect(mockMkdir).toHaveBeenCalled())

    rerender(<ProjectPage project={{ id: 'pb', name: 'B' }} />)
    await screen.findByText('b-only.txt')

    resolveMkdir({})                                        // A's run() resumes: refresh('pa')
    await new Promise(r => setTimeout(r, 0))
    await new Promise(r => setTimeout(r, 0))
    expect(screen.queryByText('a-only.txt')).toBeNull()
    expect(screen.getByText('b-only.txt')).toBeTruthy()
  })
})

describe('ProjectPage stale-mutation success remap guard (regression: codex 4.2)', () => {
  it('a move finishing after a project switch cannot remap the new project\'s selection', async () => {
    // Start moving docs → archive in project A, switch to project B (which
    // has its own docs/inner), select B's docs/inner, THEN let A's move
    // resolve. run()'s success must be project-bound, or the stale
    // handler's remap would drag B's selection to A's destination.
    const treeB = [
      { name: 'docs', path: 'docs', type: 'dir', modified_at: 1, children: [
        { name: 'inner', path: 'docs/inner', type: 'dir', modified_at: 1, children: [] },
      ] },
    ]
    mockTree.mockImplementation((pid) =>
      Promise.resolve({ tree: pid === 'pb' ? treeB : TREE }))
    let resolveMove
    mockMove.mockImplementation(() => new Promise(res => { resolveMove = res }))

    const { rerender } = render(<ProjectPage project={{ id: 'pa', name: 'A' }} />)
    await screen.findByTestId('file-row-readme.md')
    dragAndDrop(screen.getByTestId('tree-node-docs'), screen.getByTestId('tree-node-archive'))
    await waitFor(() => expect(mockMove).toHaveBeenCalledWith('pa', 'docs', 'archive/docs'))

    rerender(<ProjectPage project={{ id: 'pb', name: 'B' }} />)
    await screen.findByTestId('tree-node-docs')
    fireEvent.click(screen.getByLabelText('Expand docs'))
    fireEvent.click(screen.getByTestId('tree-node-docs/inner'))
    expect(screen.getByTestId('crumb-docs/inner')).toBeTruthy()

    resolveMove({}) // A's moveInto resumes against B's rendered state
    await new Promise(r => setTimeout(r, 0))
    await new Promise(r => setTimeout(r, 0))
    // B's selection is untouched — not remapped to A's destination, not
    // knocked back to the root by the missing-path fallback.
    expect(screen.getByTestId('crumb-docs/inner')).toBeTruthy()
    expect(screen.queryByTestId('crumb-archive/docs/inner')).toBeNull()
  })
})

describe('ProjectPage stale-refresh generation theft', () => {
  it('a stale mutation follow-up cannot invalidate the pending fetch of the current project', async () => {
    // Ordering: A's mutation pending → switch to B (B's tree fetch stays
    // pending) → A's mutation resolves and its follow-up refresh runs →
    // THEN B's fetch resolves. The stale refresh must not claim a newer
    // generation, or B's own result would be rejected and the page would
    // strand on the empty state.
    const treeA = [{ name: 'a-only.txt', path: 'a-only.txt', type: 'file', size: 1, modified_at: 1 }]
    const treeB = [{ name: 'b-only.txt', path: 'b-only.txt', type: 'file', size: 1, modified_at: 1 }]
    let resolveB
    mockTree.mockImplementation((pid) => {
      if (pid === 'pb') return new Promise(res => { resolveB = res })
      return Promise.resolve({ tree: treeA })
    })
    let resolveMkdir
    mockMkdir.mockImplementation(() => new Promise(res => { resolveMkdir = res }))
    vi.spyOn(window, 'prompt').mockReturnValue('slow-dir')

    const { rerender } = render(<ProjectPage project={{ id: 'pa', name: 'A' }} />)
    await screen.findByText('a-only.txt')
    fireEvent.click(screen.getByText('New folder'))          // A's mutation, pending
    await waitFor(() => expect(mockMkdir).toHaveBeenCalled())

    rerender(<ProjectPage project={{ id: 'pb', name: 'B' }} />)
    await waitFor(() => expect(resolveB).toBeTruthy())       // B's fetch in flight

    resolveMkdir({})                                         // stale A follow-up refresh runs first
    await new Promise(r => setTimeout(r, 0))
    resolveB({ tree: treeB })                                // B resolves LAST
    expect(await screen.findByText('b-only.txt')).toBeTruthy()
    expect(screen.queryByText('a-only.txt')).toBeNull()
  })
})
