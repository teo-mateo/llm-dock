// Pure decision behind ChatPage's create-and-send retry, in its own module for
// the same reason pendingFlush.js exists: react-refresh wants no component
// exports here, and the branch is worth testing without mounting the page.
//
// The server answers a level the service doesn't offer with 400 + this code
// (chat/routes.py:INVALID_LEVEL_CODE). Only that rejection is worth retrying:
// creating the conversation a second time after an unrelated failure — a 401, a
// 500, a body the server rejected for another reason — would duplicate a
// conversation whose first create may well have succeeded.

export const INVALID_LEVEL_CODE = "invalid_reasoning_level"

export function isReasoningLevelRejection(err) {
  return !!err && err.code === INVALID_LEVEL_CODE
}
