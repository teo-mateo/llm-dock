import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup, within } from '@testing-library/react'
import ProjectPage from './ProjectPage'

const { mockTree, mockUpload, mockMkdir, mockMove, mockDelete } = vi.hoisted(() => ({
  mockTree: vi.fn(),
  mockUpload: vi.fn(),
  mockMkdir: vi.fn(),
  mockMove: vi.fn(),
  mockDelete: vi.fn(),
}))
vi.mock('../../services/chat', () => ({
  getProjectFilesTree: (...a) => mockTree(...a),
  uploadProjectFile: (...a) => mockUpload(...a),
  mkdirProjectPath: (...a) => mockMkdir(...a),
  moveProjectPath: (...a) => mockMove(...a),
  deleteProjectPath: (...a) => mockDelete(...a),
  downloadProjectFile: vi.fn(),
}))

const project = { id: 'p1', name: 'Research', description: 'notes & data' }

const TREE = [
  {
    name: 'docs', path: 'docs', type: 'dir', modified_at: 1, children: [
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
  mockDelete.mockReset().mockResolvedValue({ ok: true })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

async function renderPage() {
  render(<ProjectPage project={project} />)
  await waitFor(() => expect(mockTree).toHaveBeenCalledWith('p1'))
  await screen.findByText('readme.md')
}

describe('ProjectPage file tree', () => {
  it('renders header, root entries, and dir contents after expand', async () => {
    await renderPage()
    expect(screen.getByText('Research')).toBeTruthy()
    expect(screen.getByText('notes & data')).toBeTruthy()
    expect(screen.getByText('docs')).toBeTruthy()
    // Children hidden until the dir is expanded.
    expect(screen.queryByText('a.txt')).toBeNull()
    fireEvent.click(screen.getByTestId('file-row-docs'))
    expect(screen.getByText('a.txt')).toBeTruthy()
  })

  it('renders a "Project not found" state without a project', () => {
    render(<ProjectPage project={null} />)
    expect(screen.getByText('Project not found')).toBeTruthy()
    expect(mockTree).not.toHaveBeenCalled()
  })

  it('creates a folder at root via prompt and refreshes', async () => {
    await renderPage()
    vi.spyOn(window, 'prompt').mockReturnValue('new-folder')
    fireEvent.click(screen.getByText('New folder'))
    await waitFor(() => expect(mockMkdir).toHaveBeenCalledWith('p1', 'new-folder'))
    expect(mockTree).toHaveBeenCalledTimes(2)
  })

  it('creates a subfolder inside a dir from its hover action', async () => {
    await renderPage()
    vi.spyOn(window, 'prompt').mockReturnValue('sub')
    fireEvent.click(screen.getByLabelText('New subfolder in docs'))
    await waitFor(() => expect(mockMkdir).toHaveBeenCalledWith('p1', 'docs/sub'))
  })

  it('uploads picked files into the chosen directory', async () => {
    await renderPage()
    fireEvent.click(screen.getByLabelText('Upload into docs'))
    const file = new File(['hello'], 'up.txt', { type: 'text/plain' })
    fireEvent.change(screen.getByTestId('file-input'), { target: { files: [file] } })
    await waitFor(() => expect(mockUpload).toHaveBeenCalledWith('p1', file, { dir: 'docs' }))
    expect(mockTree).toHaveBeenCalledTimes(2)
  })

  it('offers overwrite when the upload conflicts', async () => {
    mockUpload
      .mockRejectedValueOnce(new Error('file already exists'))
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

describe('ProjectPage upload row visibility', () => {
  it('expands the target dir after uploading into it', async () => {
    await renderPage()
    fireEvent.click(within(screen.getByTestId('file-row-docs')).getByLabelText('Upload into docs'))
    const file = new File(['hello'], 'up.txt', { type: 'text/plain' })
    fireEvent.change(screen.getByTestId('file-input'), { target: { files: [file] } })
    await waitFor(() => expect(mockUpload).toHaveBeenCalled())
    // docs auto-expanded → its child is visible.
    expect(await screen.findByText('a.txt')).toBeTruthy()
  })
})
