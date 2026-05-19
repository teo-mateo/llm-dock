import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import ChatArea from './ChatArea'

// useRunningServices (pulled in transitively by the empty-state composer's
// ChatInput-less path is fine, but ChatArea itself doesn't use it). We only
// exercise the no-conversation branches here, so no router/hook mocking is
// needed beyond what ChatArea's own imports require.
vi.mock('../../hooks/useRunningServices', () => ({
  default: () => ({ services: [], loading: false }),
}))

describe('ChatArea no-conversation states', () => {
  it('shows the create composer when there is no route conversation', () => {
    const { container } = render(
      <ChatArea
        conversation={null}
        awaitingConversation={false}
        defaultModelName="vllm-test"
        onCreateAndSend={() => {}}
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
      />
    )
    expect(container.textContent).toContain('Start a new conversation')
    expect(container.querySelector('textarea')).toBeTruthy()
  })

  it('shows a loading state (no composer) while a URL conversation is fetching', () => {
    // Regression for codex iteration 1 P1: opening /v2/chat/<id> directly
    // leaves `conversation` null during loadConversation — the empty-state
    // composer must NOT render, or typing would create a different chat.
    const { container } = render(
      <ChatArea
        conversation={null}
        awaitingConversation={true}
        defaultModelName="vllm-test"
        onCreateAndSend={() => {}}
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
      />
    )
    expect(container.textContent).toContain('Loading conversation')
    expect(container.textContent).not.toContain('Start a new conversation')
    expect(container.querySelector('textarea')).toBeNull()
  })
})
