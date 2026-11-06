import { describe, it, expect } from 'vitest'
import { buildTranscript } from './piTranscript'

const event = (seq, type, payload) => ({ seq, type, ts: seq * 1000, payload })

describe('buildTranscript', () => {
  it('deltas stream into one open assistant item', () => {
    const { items } = buildTranscript([
      event(1, 'assistant_delta', { text: 'Hel', thinking: 'th' }),
      event(2, 'assistant_delta', { text: 'lo', thinking: 'ink' }),
    ])
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      kind: 'assistant',
      id: 'a1',
      text: 'Hello',
      thinking: 'think',
      streaming: true,
    })
  })

  it('assistant_message replaces streamed text with the final text', () => {
    const usage = { input: 1, output: 2, total_tokens: 3 }
    const { items } = buildTranscript([
      event(1, 'assistant_delta', { text: 'partial', thinking: 'part' }),
      event(2, 'assistant_message', {
        text: 'final',
        thinking: 'full think',
        model: { provider: 'mistral', id: 'small' },
        usage,
        stop_reason: 'stop',
      }),
    ])
    expect(items[0]).toMatchObject({
      id: 'a1',
      text: 'final',
      thinking: 'full think',
      streaming: false,
      model: 'mistral/small',
      usage,
      stopReason: 'stop',
    })
  })

  it('assistant_message without deltas creates a closed item', () => {
    const { items } = buildTranscript([
      event(4, 'assistant_message', {
        text: 'final',
        thinking: '',
        model: null,
        usage: null,
        stop_reason: 'stop',
      }),
    ])
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      kind: 'assistant',
      id: 'a4',
      text: 'final',
      streaming: false,
      model: null,
    })
  })

  it('user message closes an open assistant item', () => {
    const { items } = buildTranscript([
      event(1, 'assistant_delta', { text: 'partial', thinking: '' }),
      event(2, 'user_message', {
        text: 'hello',
        image_count: 1,
        origin: 'terminal',
      }),
    ])
    expect(items.map((item) => item.kind)).toEqual(['assistant', 'user'])
    expect(items[0].streaming).toBe(false)
    expect(items[1]).toMatchObject({
      id: 'u2',
      text: 'hello',
      imageCount: 1,
      origin: 'terminal',
    })
  })

  it('tool lifecycle start update end', () => {
    const { items } = buildTranscript([
      event(1, 'tool_start', {
        call_id: 'c1',
        name: 'search',
        args: '{"q":"x"}',
        truncated: false,
      }),
      event(2, 'tool_update', {
        call_id: 'c1',
        name: 'search',
        partial: '{"hits":',
        truncated: true,
      }),
      event(3, 'tool_end', {
        call_id: 'c1',
        name: 'search',
        result: '{"hits":1}',
        is_error: false,
        duration_ms: 12,
        truncated: false,
      }),
    ])
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      kind: 'tool',
      id: 'tc1',
      callId: 'c1',
      name: 'search',
      args: '{"q":"x"}',
      output: '{"hits":1}',
      status: 'done',
      durationMs: 12,
      truncated: true,
    })
  })

  it('tool error status', () => {
    const { items } = buildTranscript([
      event(1, 'tool_start', { call_id: 'c1', name: 'search', args: null, truncated: false }),
      event(2, 'tool_end', {
        call_id: 'c1',
        name: 'search',
        result: 'boom',
        is_error: true,
        duration_ms: 5,
        truncated: false,
      }),
    ])
    expect(items[0].status).toBe('error')
    expect(items[0].output).toBe('boom')
  })

  it('tool update for unknown call creates the card', () => {
    const { items } = buildTranscript([
      event(1, 'tool_update', {
        call_id: 'c2',
        name: 'read',
        partial: 'abc',
        truncated: true,
      }),
    ])
    expect(items[0]).toMatchObject({
      kind: 'tool',
      id: 'tc2',
      callId: 'c2',
      name: 'read',
      args: null,
      output: 'abc',
      status: 'running',
      truncated: true,
    })
  })

  it('truncated is sticky', () => {
    const { items } = buildTranscript([
      event(1, 'tool_start', { call_id: 'c1', name: 'x', args: null, truncated: false }),
      event(2, 'tool_update', {
        call_id: 'c1',
        name: 'x',
        partial: null,
        truncated: true,
      }),
      event(3, 'tool_end', {
        call_id: 'c1',
        name: 'x',
        result: null,
        is_error: false,
        duration_ms: null,
        truncated: false,
      }),
    ])
    expect(items[0].truncated).toBe(true)
  })

  it('model and thinking notices', () => {
    const { items } = buildTranscript([
      event(1, 'model_changed', {
        previous: { provider: 'a', id: '1' },
        model: { provider: 'b', id: '2' },
      }),
      event(2, 'thinking_changed', { previous: 'low', level: 'high' }),
    ])
    expect(items[0].change).toEqual({ label: 'Model', from: 'a/1', to: 'b/2' })
    expect(items[1].change).toEqual({ label: 'Thinking', from: 'low', to: 'high' })
    expect(items[0].text).toBeUndefined()
    expect(items[1].text).toBeUndefined()
  })

  it('model notice keeps a model id holding the separator', () => {
    const { items } = buildTranscript([
      event(1, 'model_changed', {
        previous: { provider: 'x', id: 'old' },
        model: { provider: 'x', id: 'a → b' },
      }),
    ])
    expect(items[0].change.to).toBe('x/a → b')
  })

  it('compaction notice with and without tokens', () => {
    const { items } = buildTranscript([
      event(1, 'compaction', { summary: 'x', tokens_before: 123, reason: 'auto' }),
      event(2, 'compaction', { summary: 'y', tokens_before: null, reason: 'auto' }),
    ])
    expect(items.map((item) => item.text)).toEqual([
      'Context compacted (123 tokens)',
      'Context compacted',
    ])
    expect(items.map((item) => item.change)).toEqual([undefined, undefined])
  })

  it('gap notice counts missing events', () => {
    const { items } = buildTranscript([
      event(1, 'gap', { from_seq: 5, to_seq: 7 }),
    ])
    expect(items[0].text).toBe('3 events missing (5–7)')
    expect(items[0].change).toBeUndefined()
  })

  it('state turn_end and unknown types add no items', () => {
    const { items } = buildTranscript([
      event(1, 'state', { state: 'idle' }),
      event(2, 'turn_end', { outcome: 'completed' }),
      event(3, 'future_type', { anything: true }),
    ])
    expect(items).toEqual([])
  })

  it('working follows the last state event', () => {
    expect(
      buildTranscript([
        event(1, 'state', { state: 'working' }),
        event(2, 'state', { state: 'idle' }),
      ]).working,
    ).toBe(false)
    expect(
      buildTranscript([
        event(1, 'state', { state: 'idle' }),
        event(2, 'state', { state: 'working' }),
      ]).working,
    ).toBe(true)
  })

  it('ids are stable across rebuilds', () => {
    const events = [
      event(1, 'user_message', { text: 'hi', image_count: 0, origin: 'terminal' }),
      event(2, 'assistant_delta', { text: 'a', thinking: '' }),
      event(3, 'assistant_message', {
        text: 'a',
        thinking: '',
        model: null,
        usage: null,
        stop_reason: 'stop',
      }),
      event(4, 'tool_start', { call_id: 'c1', name: 'x', args: null, truncated: false }),
      event(5, 'gap', { from_seq: 6, to_seq: 6 }),
    ]
    expect(buildTranscript(events)).toEqual(buildTranscript(events))
  })
})
