import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import ProjectChatSplit from './ProjectChatSplit'

const { mockFilesTree, mockGetFileContent, mockSaveFileContent, mockUpload } = vi.hoisted(() => ({
  mockFilesTree: vi.fn(),
  mockGetFileContent: vi.fn(),
  mockSaveFileContent: vi.fn(),
  mockUpload: vi.fn(),
}))
vi.mock('../../services/chat', () => ({
  getProjectFilesTree: (...a) => mockFilesTree(...a),
  uploadProjectFile: (...a) => mockUpload(...a),
  getProjectFileContent: (...a) => mockGetFileContent(...a),
  saveProjectFileContent: (...a) => mockSaveFileContent(...a),
}))

const project = { id: 'p1', name: 'Fancy Project' }

beforeEach(() => {
  localStorage.clear()
  mockFilesTree.mockReset().mockResolvedValue({
    tree: [{ name: 'a.md', path: 'a.md', type: 'file', size: 3 }],
  })
  mockGetFileContent.mockReset().mockResolvedValue({ path: 'a.md', content: 'hello', revision: 'r1' })
  mockSaveFileContent.mockReset().mockResolvedValue({ name: 'a.md', path: 'a.md', type: 'file' })
  mockUpload.mockReset().mockResolvedValue({ ok: true })
})

afterEach(() => {
  cleanup()
  localStorage.clear()
})

describe('ProjectChatSplit', () => {
  it('renders only the chat when the conversation has no project', () => {
    render(
      <ProjectChatSplit project={null} conversationId="c1">
        <div data-testid="the-chat" />
      </ProjectChatSplit>
    )
    expect(screen.getByTestId('the-chat')).toBeInTheDocument()
    expect(screen.queryByTestId('project-chat-split')).toBeNull()
  })

  it('shows the explorer strip at the 20% default next to the chat for a project conversation', async () => {
    render(
      <ProjectChatSplit project={project} conversationId="c1">
        <div data-testid="the-chat" />
      </ProjectChatSplit>
    )
    expect(screen.getByTestId('the-chat')).toBeInTheDocument()
    const strip = screen.getByTestId('explorer-strip')
    expect(strip.style.width).toBe('20%')
    await waitFor(() => expect(screen.getByTestId('tree-node-a.md')).toBeInTheDocument())
  })

  it('collapses to a rail and expands back, persisting the choice', async () => {
    render(
      <ProjectChatSplit project={project} conversationId="c1">
        <div data-testid="the-chat" />
      </ProjectChatSplit>
    )
    await waitFor(() => expect(screen.getByTestId('tree-node-a.md')).toBeInTheDocument())

    fireEvent.click(screen.getByLabelText('Hide file explorer'))
    // The strip stays mounted (in-flight pane work must survive a
    // collapse) but is hidden.
    expect(screen.getByTestId('explorer-strip')).not.toBeVisible()
    expect(localStorage.getItem('llmdock.chatExplorer.collapsed')).toBe('true')
    // Chat stays visible while collapsed.
    expect(screen.getByTestId('the-chat')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Show file explorer'))
    expect(screen.getByTestId('explorer-strip')).toBeVisible()
    expect(localStorage.getItem('llmdock.chatExplorer.collapsed')).toBe('false')
  })

  it('drag on the divider resizes the strip within bounds and persists the width', async () => {
    const rectSpy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
      left: 0, top: 0, right: 1000, bottom: 800, width: 1000, height: 800, x: 0, y: 0, toJSON: () => {},
    })
    render(
      <ProjectChatSplit project={project} conversationId="c1">
        <div data-testid="the-chat" />
      </ProjectChatSplit>
    )
    await waitFor(() => expect(screen.getByTestId('tree-node-a.md')).toBeInTheDocument())

    fireEvent.mouseDown(screen.getByTestId('explorer-divider'))
    fireEvent.mouseMove(window, { clientX: 300 })
    expect(screen.getByTestId('explorer-strip').style.width).toBe('300px')

    // Clamped to 45% of the container (450px of 1000px)…
    fireEvent.mouseMove(window, { clientX: 900 })
    expect(screen.getByTestId('explorer-strip').style.width).toBe('450px')
    // …and to the minimum on the other side.
    fireEvent.mouseMove(window, { clientX: 10 })
    expect(screen.getByTestId('explorer-strip').style.width).toBe('160px')

    fireEvent.mouseUp(window)
    expect(localStorage.getItem('llmdock.chatExplorer.width')).toBe('160')
    rectSpy.mockRestore()
  })

  it('opening a file overlays the editor on the chat; closing removes it', async () => {
    render(
      <ProjectChatSplit project={project} conversationId="c1">
        <div data-testid="the-chat" />
      </ProjectChatSplit>
    )
    await waitFor(() => expect(screen.getByTestId('tree-node-a.md')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('tree-node-a.md'))
    await waitFor(() => expect(screen.getByTestId('editor-overlay')).toBeInTheDocument())
    expect(mockGetFileContent).toHaveBeenCalledWith('p1', 'a.md')
    // Chat stays mounted underneath.
    expect(screen.getByTestId('the-chat')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Close editor'))
    expect(screen.queryByTestId('editor-overlay')).toBeNull()
  })

  it('switching conversation closes the editor overlay', async () => {
    const { rerender } = render(
      <ProjectChatSplit project={project} conversationId="c1">
        <div data-testid="the-chat" />
      </ProjectChatSplit>
    )
    await waitFor(() => expect(screen.getByTestId('tree-node-a.md')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('tree-node-a.md'))
    await waitFor(() => expect(screen.getByTestId('editor-overlay')).toBeInTheDocument())

    rerender(
      <ProjectChatSplit project={project} conversationId="c2">
        <div data-testid="the-chat" />
      </ProjectChatSplit>
    )
    expect(screen.queryByTestId('editor-overlay')).toBeNull()
  })

  it('a dirty editor asks before opening another file', async () => {
    mockFilesTree.mockResolvedValue({
      tree: [
        { name: 'a.md', path: 'a.md', type: 'file', size: 3 },
        { name: 'b.md', path: 'b.md', type: 'file', size: 3 },
      ],
    })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(
      <ProjectChatSplit project={project} conversationId="c1">
        <div data-testid="the-chat" />
      </ProjectChatSplit>
    )
    await waitFor(() => expect(screen.getByTestId('tree-node-a.md')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('tree-node-a.md'))
    await waitFor(() => expect(screen.getByTestId('editor-textarea')).toBeInTheDocument())

    fireEvent.change(screen.getByTestId('editor-textarea'), { target: { value: 'edited' } })
    fireEvent.click(screen.getByTestId('tree-node-b.md'))
    expect(confirmSpy).toHaveBeenCalled()
    // Declined: still editing a.md.
    expect(screen.getByTestId('editor-textarea').value).toBe('edited')

    confirmSpy.mockReturnValue(true)
    fireEvent.click(screen.getByTestId('tree-node-b.md'))
    await waitFor(() => expect(mockGetFileContent).toHaveBeenCalledWith('p1', 'b.md'))
    confirmSpy.mockRestore()
  })
})

describe('ProjectChatSplit parent-rerender stability (regression: PR #87 codex 1.1)', () => {
  it('keeps a dirty editor open when the parent rerenders with a fresh dirty-callback identity', async () => {
    // ChatPage passes onEditorDirtyChange as an inline lambda, so its
    // identity changes every parent render (each streaming delta). That
    // must not re-fire the editor-reset effect.
    const { rerender } = render(
      <ProjectChatSplit project={project} conversationId="c1" onEditorDirtyChange={() => {}}>
        <div data-testid="the-chat" />
      </ProjectChatSplit>
    )
    await waitFor(() => expect(screen.getByTestId('tree-node-a.md')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('tree-node-a.md'))
    await waitFor(() => expect(screen.getByTestId('editor-textarea')).toBeInTheDocument())
    fireEvent.change(screen.getByTestId('editor-textarea'), { target: { value: 'edited' } })

    for (let i = 0; i < 3; i++) {
      rerender(
        <ProjectChatSplit project={project} conversationId="c1" onEditorDirtyChange={() => {}}>
          <div data-testid="the-chat" />
        </ProjectChatSplit>
      )
    }

    expect(screen.getByTestId('editor-overlay')).toBeInTheDocument()
    expect(screen.getByTestId('editor-textarea').value).toBe('edited')
  })
})

describe('ProjectChatSplit restored-width clamping (regression: PR #87 codex 2.3)', () => {
  it('clamps a stored width from a wider display to 45% of the current container', async () => {
    const rectSpy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
      left: 0, top: 0, right: 1000, bottom: 800, width: 1000, height: 800, x: 0, y: 0, toJSON: () => {},
    })
    localStorage.setItem('llmdock.chatExplorer.width', '800')
    render(
      <ProjectChatSplit project={project} conversationId="c1">
        <div data-testid="the-chat" />
      </ProjectChatSplit>
    )
    await waitFor(() => expect(screen.getByTestId('tree-node-a.md')).toBeInTheDocument())
    // 800px stored, container 1000px → clamped to 450px at render.
    expect(screen.getByTestId('explorer-strip').style.width).toBe('450px')
    rectSpy.mockRestore()
  })
})

describe('ProjectChatSplit in-flight upload survives collapse (regression: PR #87 codex 3.3)', () => {
  it('an upload started before collapsing lands in the visible tree after re-expand', async () => {
    let resolveUpload
    mockUpload.mockImplementationOnce(() => new Promise(r => { resolveUpload = r }))
    render(
      <ProjectChatSplit project={project} conversationId="c1">
        <div data-testid="the-chat" />
      </ProjectChatSplit>
    )
    await waitFor(() => expect(screen.getByTestId('tree-node-a.md')).toBeInTheDocument())
    expect(mockFilesTree).toHaveBeenCalledTimes(1)

    // Start an upload, then collapse while it is still in flight.
    const file = new File(['x'], 'up.txt', { type: 'text/plain' })
    fireEvent.change(screen.getByTestId('explorer-file-input'), { target: { files: [file] } })
    fireEvent.click(screen.getByLabelText('Hide file explorer'))

    // Re-expand, then let the upload finish: its follow-up refresh must
    // hit the pane the user sees (the pane stayed mounted throughout).
    fireEvent.click(screen.getByLabelText('Show file explorer'))
    mockFilesTree.mockResolvedValueOnce({
      tree: [
        { name: 'a.md', path: 'a.md', type: 'file', size: 3 },
        { name: 'up.txt', path: 'up.txt', type: 'file', size: 1 },
      ],
    })
    resolveUpload({ ok: true })
    await waitFor(() => expect(screen.getByTestId('tree-node-up.txt')).toBeInTheDocument())
  })
})
