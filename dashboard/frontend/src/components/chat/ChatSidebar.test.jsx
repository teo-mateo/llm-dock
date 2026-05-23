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

// Returns the label that wraps the conversation row's checkbox. The
// label is the actual click target — it's a 32px hit area around a 14px
// <input>, and the toggle handler lives on the label so that clicks on
// the padding behave the same as clicks on the input itself.
function checkboxFor(title) {
  const titleNode = screen.getByText(title)
  const row = titleNode.closest('.group')
  return within(row).getByRole('checkbox').closest('label')
}

function selectedTitles() {
  // All checked checkboxes, mapped back to their row's title text. Order
  // matches the rendered DOM order, which is the same as flatOrder.
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

  // Note: the in-real-browsers scenario where the user clicks directly
  // on the visible 14px <input> (whose click bubbles up to the label's
  // onClick) cannot be reproduced under jsdom — its label activation
  // model doesn't propagate input clicks to a wrapping label's onClick
  // the way real browsers do. The label-padding tests above (which click
  // the label element directly) cover the case codex iter 2 actually
  // flagged: the synthetic activation when the user clicks the larger
  // hit target. Direct-input clicks are exercised manually in the
  // browser as part of the PR's test plan.

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
