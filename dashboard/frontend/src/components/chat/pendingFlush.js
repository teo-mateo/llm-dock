// Pure decision for ChatPage's queued first-message flush. Lives in its
// own module (not ChatPage.jsx) so react-refresh stays happy and the
// codex-iter-3 race (a stale getConversation resolving for an abandoned
// route) is unit-testable without router/hook mocking.
//   'wait'    — keep the pending message; conditions not yet met
//   'abandon' — drop it; the route no longer points at the pending chat
//   'send'    — route + loaded conversation match and not streaming
export function pendingFlushDecision(pending, convId, conversation, streaming) {
  if (!pending) return 'wait'
  if (convId !== pending.convId) return 'abandon'
  if (conversation && conversation.id === pending.convId && !streaming) return 'send'
  return 'wait'
}
