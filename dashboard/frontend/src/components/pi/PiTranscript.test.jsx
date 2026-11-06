import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import PiTranscript from './PiTranscript'

const notice = (id) => ({ kind: 'notice', id: `n${id}`, text: `note ${id}`, ts: id })

function scrollable(container, { scrollTop }) {
  Object.defineProperty(container, 'scrollHeight', { configurable: true, value: 1000 })
  Object.defineProperty(container, 'clientHeight', { configurable: true, value: 200 })
  container.scrollTop = scrollTop
}

afterEach(cleanup)

describe('PiTranscript', () => {
  it('follows new content while at the bottom', () => {
    const { rerender } = render(<PiTranscript items={[notice(1)]} working={false} lastStopAt={null} />)
    const container = screen.getByTestId('pi-transcript')
    scrollable(container, { scrollTop: 800 })
    rerender(<PiTranscript items={[notice(1), notice(2)]} working={false} lastStopAt={null} />)
    expect(container.scrollTop).toBe(1000)
    expect(screen.queryByText('New content ↓')).not.toBeInTheDocument()
  })

  it('scrolled up shows a new content button that jumps back and resumes following', () => {
    const { rerender } = render(<PiTranscript items={[notice(1)]} working={false} lastStopAt={null} />)
    const container = screen.getByTestId('pi-transcript')
    scrollable(container, { scrollTop: 0 })
    fireEvent.scroll(container)
    rerender(<PiTranscript items={[notice(1), notice(2)]} working={false} lastStopAt={null} />)
    expect(container.scrollTop).toBe(0)
    fireEvent.click(screen.getByRole('button', { name: 'New content ↓' }))
    expect(container.scrollTop).toBe(1000)
    expect(screen.queryByText('New content ↓')).not.toBeInTheDocument()
    rerender(<PiTranscript items={[notice(1), notice(2), notice(3)]} working={false} lastStopAt={null} />)
    expect(screen.queryByText('New content ↓')).not.toBeInTheDocument()
  })

  it('no button when nothing new arrived after scrolling up', () => {
    render(<PiTranscript items={[notice(1)]} working={false} lastStopAt={null} />)
    const container = screen.getByTestId('pi-transcript')
    scrollable(container, { scrollTop: 0 })
    fireEvent.scroll(container)
    expect(screen.queryByText('New content ↓')).not.toBeInTheDocument()
  })
})
