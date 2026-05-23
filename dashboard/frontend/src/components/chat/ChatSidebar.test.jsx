import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react'
import ChatSidebar from './ChatSidebar'

// ThemeSwitcher pulls in unrelated context (icons, theme store). Stub it.
vi.mock('../ThemeSwitcher', () => ({ default: () => null }))

afterEach(() => cleanup())

// Tree shape used by the range tests:
//   A
//     A1   (spinoff of A)
//   B
//   C
//     C1   (spinoff of C)
//   D
// flatOrder (depth-first) is therefore: A, A1, B, C, C1, D.
const conversations = [
  { id: 'A',  title: 'A',  parent_conversation_id: null, updated_at: '2026-01-01' },
  { id: 'A1', title: 'A1', parent_conversation_id: 'A',  updated_at: '2026-01-01' },
  { id: 'B',  title: 'B',  parent_conversation_id: null, updated_at: '2026-01-01' },
  { id: 'C',  title: 'C',  parent_conversation_id: null, updated_at: '2026-01-01' },
  { id: 'C1', title: 'C1', parent_conversation_id: 'C',  updated_at: '2026-01-01' },
  { id: 'D',  title: 'D',  parent_conversation_id: null, updated_at: '2026-01-01' },
]

function renderSidebar() {
  return render(
    <ChatSidebar
      conversations={conversations}
      activeId={null}
      onSelect={() => {}}
      onCreate={() => {}}
      onDelete={() => {}}
      onDeleteMany={() => {}}
    />
  )
}

// Returns the checkbox <input> for the conversation row titled `title`.
// Each row's title sits next to its checkbox inside the row container.
function checkboxFor(title) {
  const titleNode = screen.getByText(title)
  const row = titleNode.closest('.group')
  return within(row).getByRole('checkbox')
}

function selectedTitles() {
  // All checked checkboxes, mapped back to their row's title text.
  return screen
    .getAllByRole('checkbox')
    .filter(cb => cb.checked)
    .map(cb => within(cb.closest('.group')).getAllByText(/^[A-Z]\d?$/)[0].textContent)
}

describe('ChatSidebar shift-click range selection', () => {
  it('plain click toggles a single row and sets the anchor', () => {
    renderSidebar()
    fireEvent.click(checkboxFor('B'))
    expect(selectedTitles()).toEqual(['B'])
  })

  it('shift-click without an anchor falls back to a single toggle', () => {
    renderSidebar()
    // First interaction is a shift-click — no prior anchor exists, so it
    // should just toggle the clicked row.
    fireEvent.click(checkboxFor('C'), { shiftKey: true })
    expect(selectedTitles()).toEqual(['C'])
  })

  it('shift-click selects the inclusive depth-first range between anchor and clicked', () => {
    renderSidebar()
    fireEvent.click(checkboxFor('A'))                       // anchor = A
    fireEvent.click(checkboxFor('C1'), { shiftKey: true })  // range A..C1
    // flatOrder slice from A to C1 is A, A1, B, C, C1.
    expect(selectedTitles()).toEqual(['A', 'A1', 'B', 'C', 'C1'])
  })

  it('range works in reverse (clicked above anchor) and includes both endpoints', () => {
    renderSidebar()
    fireEvent.click(checkboxFor('D'))                      // anchor = D
    fireEvent.click(checkboxFor('A1'), { shiftKey: true }) // range A1..D
    expect(selectedTitles()).toEqual(['A1', 'B', 'C', 'C1', 'D'])
  })

  it('anchor persists across consecutive shift-clicks (Finder/Gmail behavior)', () => {
    renderSidebar()
    fireEvent.click(checkboxFor('A'))                      // anchor = A
    fireEvent.click(checkboxFor('B'), { shiftKey: true })  // range A..B
    fireEvent.click(checkboxFor('D'), { shiftKey: true })  // range A..D, anchor still A
    expect(selectedTitles()).toEqual(['A', 'A1', 'B', 'C', 'C1', 'D'])
  })

  it('Clear resets the anchor so the next shift-click no longer extends the old range', () => {
    renderSidebar()
    fireEvent.click(checkboxFor('A'))                       // anchor = A
    fireEvent.click(checkboxFor('B'), { shiftKey: true })   // range A..B
    fireEvent.click(screen.getByTitle('Clear selection'))   // clears + drops anchor

    // With the anchor gone, a fresh shift-click should behave like a single
    // toggle, not extend from the cleared anchor.
    fireEvent.click(checkboxFor('D'), { shiftKey: true })
    expect(selectedTitles()).toEqual(['D'])
  })
})
