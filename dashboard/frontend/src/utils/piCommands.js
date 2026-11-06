const OUTCOME_LABELS = {
  completed: 'run completed',
  aborted: 'aborted',
  error: 'error',
}

export function commandOutcome(status, body) {
  if (status === 200 && body?.ok === true) {
    return { kind: 'done', message: null }
  }
  if (status === 200 && body?.ok === false) {
    return {
      kind: 'failed',
      message: `pi could not run it (${body.error})`,
    }
  }
  if (status === 202) {
    return { kind: 'pending', message: 'Sent — pi will pick it up' }
  }
  if (status === 409) {
    return { kind: 'rejected', message: 'pi is offline' }
  }
  if (status === 429) {
    return { kind: 'rejected', message: 'Too many messages — wait a minute' }
  }
  if (status === 503) {
    return { kind: 'rejected', message: 'The dashboard is busy — try again' }
  }
  if (status === 400 && body?.error === 'invalid_text') {
    return { kind: 'rejected', message: 'Message is empty or too long' }
  }
  return { kind: 'rejected', message: `Could not send (${status})` }
}

export function runEndLabel(outcome, runEndTs, lastStopAt) {
  if (
    lastStopAt != null &&
    Number.isFinite(runEndTs) &&
    runEndTs - lastStopAt >= 0 &&
    runEndTs - lastStopAt <= 30000
  ) {
    return 'stopped'
  }
  return OUTCOME_LABELS[outcome] ?? `run ${outcome}`
}
