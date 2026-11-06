function modelLabel(model) {
  if (!model) return null
  return `${model.provider}/${model.id}`
}

function assistantItem(seq, ts, payload, streaming) {
  return {
    kind: 'assistant',
    id: `a${seq}`,
    text: payload.text || '',
    thinking: payload.thinking || '',
    streaming,
    model: modelLabel(payload.model),
    usage: payload.usage ?? null,
    stopReason: payload.stop_reason ?? null,
    ts,
  }
}

function toolItem(ts, payload, status, output) {
  return {
    kind: 'tool',
    id: `t${payload.call_id}`,
    callId: payload.call_id,
    name: payload.name,
    args: payload.args ?? null,
    output,
    status,
    durationMs: payload.duration_ms ?? null,
    truncated: payload.truncated || false,
    ts,
  }
}

function noticeText(type, payload) {
  if (type === 'model_changed') {
    return `Model: ${modelLabel(payload.previous) || '—'} → ${modelLabel(payload.model) || '—'}`
  }
  if (type === 'thinking_changed') {
    return `Thinking: ${payload.previous || '—'} → ${payload.level || '—'}`
  }
  if (type === 'compaction') {
    const tokens =
      payload.tokens_before === null || payload.tokens_before === undefined
        ? ''
        : ` (${payload.tokens_before} tokens)`
    return `Context compacted${tokens}`
  }
  if (type === 'gap') {
    const count = payload.to_seq - payload.from_seq + 1
    return `${count} events missing (${payload.from_seq}–${payload.to_seq})`
  }
  return null
}

function closeOpen(state) {
  if (state.open) state.open.streaming = false
  state.open = null
}

function applyAssistantDelta(state, event) {
  const { seq, ts, payload } = event
  if (!state.open) {
    state.open = assistantItem(seq, ts, { text: '', thinking: '' }, true)
    state.items.push(state.open)
  }
  state.open.text += payload.text || ''
  state.open.thinking += payload.thinking || ''
}

function applyAssistantMessage(state, event) {
  const { seq, ts, payload } = event
  if (state.open) {
    state.open.text = payload.text || ''
    state.open.thinking = payload.thinking || ''
    state.open.model = modelLabel(payload.model)
    state.open.usage = payload.usage ?? null
    state.open.stopReason = payload.stop_reason ?? null
    state.open.streaming = false
    state.open = null
  } else {
    state.items.push(assistantItem(seq, ts, payload, false))
  }
}

function applyTool(state, event) {
  const { type, ts, payload } = event
  if (type === 'tool_start') {
    closeOpen(state)
    const tool = toolItem(ts, payload, 'running', null)
    state.tools.set(payload.call_id, tool)
    state.items.push(tool)
    return
  }

  let tool = state.tools.get(payload.call_id)
  if (!tool) {
    tool = toolItem(
      ts,
      payload,
      type === 'tool_end' && payload.is_error ? 'error' : type === 'tool_end' ? 'done' : 'running',
      type === 'tool_update' ? payload.partial ?? null : payload.result ?? null,
    )
    state.tools.set(payload.call_id, tool)
    state.items.push(tool)
  } else if (type === 'tool_update') {
    tool.output = payload.partial ?? null
  } else {
    tool.output = payload.result ?? null
    tool.status = payload.is_error ? 'error' : 'done'
    tool.durationMs = payload.duration_ms ?? null
  }
  tool.truncated = tool.truncated || payload.truncated
}

function applyEvent(state, event) {
  const { type, seq, ts, payload } = event
  if (type === 'state') {
    state.working = payload.state === 'working'
  } else if (type === 'user_message') {
    closeOpen(state)
    state.items.push({
      kind: 'user',
      id: `u${seq}`,
      text: payload.text,
      imageCount: payload.image_count,
      origin: payload.origin,
      ts,
    })
  } else if (type === 'assistant_delta') {
    applyAssistantDelta(state, event)
  } else if (type === 'assistant_message') {
    applyAssistantMessage(state, event)
  } else if (type === 'tool_start' || type === 'tool_update' || type === 'tool_end') {
    applyTool(state, event)
  } else if (type === 'run_end') {
    closeOpen(state)
    state.items.push({ kind: 'run_end', id: `r${seq}`, outcome: payload.outcome, ts })
  } else {
    const text = noticeText(type, payload)
    if (text) state.items.push({ kind: 'notice', id: `n${seq}`, text, ts })
  }
}

export function buildTranscript(events) {
  const state = { items: [], open: null, working: false, tools: new Map() }
  for (const event of events) applyEvent(state, event)
  return { items: state.items, working: state.working }
}
