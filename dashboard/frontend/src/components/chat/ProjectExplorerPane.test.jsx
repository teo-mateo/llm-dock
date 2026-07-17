import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import ProjectExplorerPane from './ProjectExplorerPane'

const { mockFilesTree, mockUpload } = vi.hoisted(() => ({
  mockFilesTree: vi.fn(),
  mockUpload: vi.fn(),
}))
vi.mock('../../services/chat', () => ({
  getProjectFilesTree: (...a) => mockFilesTree(...a),
  uploadProjectFile: (...a) => mockUpload(...a),
}))

const project = { id: 'p1', name: 'Fancy Project' }

const TREE = [
  {
    name: 'docs', path: 'docs', type: 'dir', children: [
      { name: 'notes.md', path: 'docs/notes.md', type: 'file', size: 10 },
    ],
  },
  { name: 'README.md', path: 'README.md', type: 'file', size: 5 },
]

beforeEach(() => {
  mockFilesTree.mockReset().mockResolvedValue({ tree: TREE })
  mockUpload.mockReset().mockResolvedValue({ ok: true })
})

afterEach(() => cleanup())

describe('ProjectExplorerPane', () => {
  it('fetches and renders the project tree; expanding a folder reveals children', async () => {
    render(<ProjectExplorerPane project={project} />)
    await waitFor(() => expect(screen.getByTestId('tree-node-README.md')).toBeInTheDocument())
    expect(mockFilesTree).toHaveBeenCalledWith('p1')
    expect(screen.getByText('Fancy Project')).toBeInTheDocument()

    // Children hidden until the folder is expanded.
    expect(screen.queryByTestId('tree-node-docs/notes.md')).toBeNull()
    fireEvent.click(screen.getByTestId('tree-node-docs'))
    expect(screen.getByTestId('tree-node-docs/notes.md')).toBeInTheDocument()
    // Clicking the folder again collapses it.
    fireEvent.click(screen.getByTestId('tree-node-docs'))
    expect(screen.queryByTestId('tree-node-docs/notes.md')).toBeNull()
  })

  it('clicking a file reports it as an existing file', async () => {
    const onOpenFile = vi.fn()
    render(<ProjectExplorerPane project={project} onOpenFile={onOpenFile} />)
    await waitFor(() => expect(screen.getByTestId('tree-node-README.md')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('tree-node-README.md'))
    expect(onOpenFile).toHaveBeenCalledWith('README.md', false)
  })

  it('collapse button invokes onCollapse', async () => {
    const onCollapse = vi.fn()
    render(<ProjectExplorerPane project={project} onCollapse={onCollapse} />)
    await waitFor(() => expect(screen.getByTestId('tree-node-README.md')).toBeInTheDocument())
    fireEvent.click(screen.getByLabelText('Hide file explorer'))
    expect(onCollapse).toHaveBeenCalled()
  })

  it('refresh button and refreshKey bumps re-read the tree', async () => {
    const { rerender } = render(<ProjectExplorerPane project={project} refreshKey={0} />)
    await waitFor(() => expect(mockFilesTree).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByLabelText('Refresh file tree'))
    await waitFor(() => expect(mockFilesTree).toHaveBeenCalledTimes(2))

    rerender(<ProjectExplorerPane project={project} refreshKey={1} />)
    await waitFor(() => expect(mockFilesTree).toHaveBeenCalledTimes(3))
  })

  it('new file prompts for a name; an unknown path opens as new, a known one as existing', async () => {
    const onOpenFile = vi.fn()
    const promptSpy = vi.spyOn(window, 'prompt')
    render(<ProjectExplorerPane project={project} onOpenFile={onOpenFile} />)
    await waitFor(() => expect(screen.getByTestId('tree-node-README.md')).toBeInTheDocument())

    promptSpy.mockReturnValueOnce('fresh.md')
    fireEvent.click(screen.getByLabelText('New file'))
    expect(onOpenFile).toHaveBeenLastCalledWith('fresh.md', true)

    promptSpy.mockReturnValueOnce('README.md')
    fireEvent.click(screen.getByLabelText('New file'))
    expect(onOpenFile).toHaveBeenLastCalledWith('README.md', false)

    promptSpy.mockRestore()
  })

  it('uploads picked files into the project root and refreshes', async () => {
    render(<ProjectExplorerPane project={project} />)
    await waitFor(() => expect(mockFilesTree).toHaveBeenCalledTimes(1))

    const file = new File(['x'], 'up.txt', { type: 'text/plain' })
    fireEvent.change(screen.getByTestId('explorer-file-input'), { target: { files: [file] } })

    await waitFor(() => expect(mockUpload).toHaveBeenCalledWith('p1', file, { dir: '' }))
    await waitFor(() => expect(mockFilesTree).toHaveBeenCalledTimes(2))
  })

  it('a stale tree response for the previous project is discarded', async () => {
    let resolveP1
    mockFilesTree.mockImplementationOnce(() => new Promise(r => { resolveP1 = r }))
    const { rerender } = render(<ProjectExplorerPane project={project} />)
    await waitFor(() => expect(mockFilesTree).toHaveBeenCalledTimes(1))

    mockFilesTree.mockResolvedValueOnce({ tree: [{ name: 'other.md', path: 'other.md', type: 'file' }] })
    rerender(<ProjectExplorerPane project={{ id: 'p2', name: 'Other' }} />)
    await waitFor(() => expect(screen.getByTestId('tree-node-other.md')).toBeInTheDocument())

    // Late p1 response must not clobber p2's rows.
    resolveP1({ tree: TREE })
    await new Promise(r => setTimeout(r, 0))
    expect(screen.queryByTestId('tree-node-README.md')).toBeNull()
    expect(screen.getByTestId('tree-node-other.md')).toBeInTheDocument()
  })
})

describe('ProjectExplorerPane mount fetch count (regression: PR #87 codex 2.4)', () => {
  it('mounting with an already-positive refreshKey issues a single tree read', async () => {
    const { rerender } = render(<ProjectExplorerPane project={project} refreshKey={3} />)
    await waitFor(() => expect(screen.getByTestId('tree-node-README.md')).toBeInTheDocument())
    await new Promise(r => setTimeout(r, 0))
    expect(mockFilesTree).toHaveBeenCalledTimes(1)

    // A later key CHANGE still refreshes.
    rerender(<ProjectExplorerPane project={project} refreshKey={4} />)
    await waitFor(() => expect(mockFilesTree).toHaveBeenCalledTimes(2))
  })
})
