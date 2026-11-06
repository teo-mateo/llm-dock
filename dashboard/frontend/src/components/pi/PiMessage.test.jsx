import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import PiMessage from './PiMessage'
import { ThemeProvider } from '../../contexts/ThemeContext'

function renderMessage(item) {
  render(
    <ThemeProvider>
      <PiMessage item={item} />
    </ThemeProvider>,
  )
}

function userItem(overrides = {}) {
  return {
    kind: 'user',
    id: 'u1',
    text: 'hello',
    imageCount: 0,
    origin: 'terminal',
    ts: 1000,
    ...overrides,
  }
}

function assistantItem(overrides = {}) {
  return {
    kind: 'assistant',
    id: 'a1',
    text: 'hello',
    thinking: '',
    streaming: false,
    model: null,
    usage: null,
    stopReason: null,
    ts: 1000,
    ...overrides,
  }
}

afterEach(cleanup)

describe('PiMessage', () => {
  it('user bubble shows from phone for extension origin', () => {
    renderMessage(userItem({ origin: 'extension', imageCount: 2 }))
    expect(screen.getByText('hello')).toBeInTheDocument()
    expect(screen.getByText('from phone')).toBeInTheDocument()
    expect(screen.getByText('+2 images')).toBeInTheDocument()
  })

  it('assistant renders markdown', () => {
    renderMessage(assistantItem({ text: 'Hello **bold**' }))
    expect(screen.getByText('bold')).toBeInTheDocument()
  })

  it('thinking is collapsed', () => {
    renderMessage(assistantItem({ thinking: 'secret thought' }))
    const details = screen.getByText('Thinking').closest('details')
    expect(details).not.toHaveAttribute('open')
  })

  it('streaming shows caret', () => {
    renderMessage(assistantItem({ streaming: true }))
    expect(screen.getByLabelText('streaming')).toBeInTheDocument()
  })
})
