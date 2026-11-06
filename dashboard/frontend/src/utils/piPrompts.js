export function needsAnswer(session) {
  if (!session || !session.live) return false
  return Array.isArray(session.prompts) && session.prompts.length > 0
}

export function pendingCount(sessions) {
  return sessions.filter(needsAnswer).length
}

export function answerLabel(value) {
  if (value === true) return 'yes'
  if (value === false) return 'no'
  if (value === null || value === undefined) return 'nothing'
  if (typeof value === 'object') return value.choice || 'decision'
  return String(value)
}

export function promptOutcome(status, body) {
  const error = body && body.error
  if (status === 200 && body && body.ok === true) {
    return { kind: 'done', message: null }
  }
  if (status === 202) {
    return { kind: 'pending', message: 'Sent — pi has not accepted it yet' }
  }
  if (status === 409 && error === 'prompt_already_answered') {
    if (body.reason && body.reason !== 'answered') {
      return { kind: 'closed', message: `Nothing to answer — the question ${body.reason}` }
    }
    return {
      kind: 'closed',
      message: `Already answered — ${answerLabel(body.value)}${body.answered_by ? ` by the ${body.answered_by}` : ''}`,
    }
  }
  if (status === 409) {
    return { kind: 'rejected', message: 'pi is offline' }
  }
  if (status === 404) {
    return { kind: 'closed', message: 'That question is no longer open' }
  }
  if (status === 429) {
    return { kind: 'rejected', message: 'Too many answers — wait a moment' }
  }
  if (status === 503) {
    return { kind: 'rejected', message: 'The dashboard is busy — try again' }
  }
  if (status === 400 && error === 'invalid_value') {
    return { kind: 'rejected', message: 'pi did not accept that answer' }
  }
  if (status === 400) {
    return { kind: 'rejected', message: 'The answer could not be sent' }
  }
  return { kind: 'rejected', message: `Could not answer (${status})` }
}
