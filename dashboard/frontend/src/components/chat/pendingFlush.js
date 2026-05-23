// Pure decision for ChatPage's queued first-message flush. Lives in its
// own module (not ChatPage.jsx) so react-refresh stays happy and the
// codex-iter-3 race (a stale getConversation resolving for an abandoned
// route) is unit-testable without router/hook mocking.
//   'wait'    — keep the pending message; conditions not yet met
//   'abandon' — drop it; the route no longer points at the pending chat
//   'send'    — route + loaded conversation match and not streaming
export function pendingFlushDecision(pending, convId, conversation, streaming) {
  if (!pending) return 'wait'
  // convId is null on the empty-state /chat render that runs after
  // handleCreateAndSend has set pendingMsgRef but before navigate() has
  // committed the URL change. Treating that as 'abandon' clears the
  // queued message before the flush effect ever gets a chance to send
  // it (the bug behind PR #46 not actually fixing /new-chat-issue).
  // Wait for the route to settle instead.
  if (!convId) return 'wait'
  if (convId !== pending.convId) return 'abandon'
  if (conversation && conversation.id === pending.convId && !streaming) return 'send'
  return 'wait'
}
