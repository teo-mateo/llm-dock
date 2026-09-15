// Pure decision behind ChatPage's create-and-send retry: only the server's
// rejection of a composer field is worth creating a second conversation for,
// because any other failure can arrive after the first create already succeeded.
// One predicate per field, because the retry drops exactly the field the code
// names — a level and a sampling set are independent saves.

export const INVALID_LEVEL_CODE = "invalid_reasoning_level"
export const INVALID_SAMPLING_CODE = "invalid_sampling_params"

export function isReasoningLevelRejection(err) {
  return !!err && err.code === INVALID_LEVEL_CODE
}

export function isSamplingParamsRejection(err) {
  return !!err && err.code === INVALID_SAMPLING_CODE
}
