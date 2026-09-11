// Pure decision behind ChatPage's create-and-send retry: only the server's
// level rejection is worth creating a second conversation for, because any other
// failure can arrive after the first create already succeeded.

export const INVALID_LEVEL_CODE = "invalid_reasoning_level"

export function isReasoningLevelRejection(err) {
  return !!err && err.code === INVALID_LEVEL_CODE
}
