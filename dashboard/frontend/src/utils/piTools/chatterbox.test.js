import { describe, it, expect } from 'vitest'
import {
  chatTime,
  joinSummary,
  leaveSummary,
  lookSummary,
  parseLook,
  parseSend,
  sendOutcomeTone,
  sendSummary,
  sendTarget,
} from './chatterbox'
import { parseToolArgs, parseToolCall, parseToolResult } from './payload'
import { genericSummary } from './summary'

function tool(name, parse, args, output = null) {
  const item = { id: 't1', name, args, output, status: 'done', durationMs: 3, truncated: false }
  return { ...parseToolCall(args, output, parse), item }
}

const sendArgs =
  '{"audience":"participant","to":"product-owner","text":"Mid-#30, no blocker. Done so far…\\n\\nNext: the drawer."}'
const confirmed =
  '{"content":[{"type":"text","text":"Sent to product-owner in #mailbox; confirmed by the server."}],"details":{"outcome":"confirmed"}}'

describe('sendTarget', () => {
  it('points at the participant, a private recipient or the channel', () => {
    expect(sendTarget(parseToolArgs(sendArgs))).toBe('→ product-owner')
    expect(sendTarget({ audience: 'private', to: 'reviewer', text: 'x' })).toBe('→ reviewer')
    expect(sendTarget({ audience: 'channel', text: 'Announcement' })).toBe('→ channel')
  })

  it('is empty without a recipient', () => {
    expect(sendTarget({ audience: 'participant', text: 'Hi' })).toBe('')
    expect(sendTarget(null)).toBe('')
  })
})

describe('parseSend', () => {
  it('reads target, text, privacy and outcome', () => {
    expect(tool('chatterbox_send', parseSend, '{"audience":"private","to":"po","text":"hi"}', confirmed).view).toEqual({
      target: '→ po',
      text: 'hi',
      private: true,
      outcome: 'confirmed',
    })
    expect(parseSend(null, null)).toBeNull()
  })

  it('tones a confirmed send green and anything else amber', () => {
    expect(sendOutcomeTone('confirmed')).toBe('success')
    expect(sendOutcomeTone('held-back')).toBe('warning')
  })
})

describe('sendSummary', () => {
  it('reads the first text line', () => {
    expect(sendSummary(tool('chatterbox_send', parseSend, sendArgs, confirmed))).toBe(
      '→ product-owner: Mid-#30, no blocker. Done so far…',
    )
  })

  it('appends an unconfirmed outcome and marks a private send', () => {
    const held = '{"content":[{"type":"text","text":"NOT SENT."}],"details":{"outcome":"held-back"}}'
    expect(sendSummary(tool('chatterbox_send', parseSend, sendArgs, held))).toBe(
      '→ product-owner: Mid-#30, no blocker. Done so far… · held-back',
    )
    expect(sendSummary(tool('chatterbox_send', parseSend, '{"audience":"private","to":"po","text":"hi"}'))).toBe(
      '→ po (private): hi',
    )
  })

  it('reads a channel audience', () => {
    expect(sendSummary(tool('chatterbox_send', parseSend, '{"audience":"channel","text":"Announcement"}', confirmed))).toBe(
      '→ channel: Announcement',
    )
  })

  it('falls back without a target', () => {
    const t = tool('chatterbox_send', parseSend, '{"audience":"participant","text":"Hi"}')
    expect(sendSummary(t)).toBe(genericSummary(t))
  })
})

describe('parseLook', () => {
  it('maps real look items to chat lines', () => {
    const output = JSON.stringify({
      content: [{ type: 'text', text: '- 12:41:58Z llmdock-po (bot): Hi all' }],
      details: {
        items: [
          { time: '2026-11-09T12:41:58Z', from: 'llmdock-po', kind: 'bot', addressed: false, important: false, private: false, text: 'Hi all, …' },
          { time: '2026-11-09T12:45:02Z', from: 'developer', kind: 'human', addressed: true, important: true, private: true, text: 'Received.\nSecond line' },
          'not an object',
        ],
      },
    })
    const { lines } = tool('chatterbox_look', parseLook, '{"what":"recent","count":10}', output).view
    expect(lines).toEqual([
      { time: '12:41', from: 'llmdock-po', bot: true, text: 'Hi all, …', important: false, private: false, toYou: false },
      { time: '12:45', from: 'developer', bot: false, text: 'Received.\nSecond line', important: true, private: true, toYou: true },
    ])
  })

  it('keeps a malformed time verbatim', () => {
    expect(chatTime('no-time')).toBe('no-time')
    expect(chatTime(null)).toBe('')
  })

  it('reads people, and has no lines without items', () => {
    const who = JSON.stringify({
      content: [{ type: 'text', text: 'architect bot\nteodor' }],
      details: { people: [{ nick: 'architect', kind: 'bot' }, { nick: 'teodor', kind: 'human' }, { kind: 'bot' }] },
    })
    expect(tool('chatterbox_look', parseLook, '{"what":"who"}', who).view).toEqual({
      what: 'who',
      count: null,
      lines: null,
      people: [
        { nick: 'architect', bot: true },
        { nick: 'teodor', bot: false },
      ],
    })
    expect(tool('chatterbox_look', parseLook, '{"what":"status"}', confirmed).view).toMatchObject({ lines: null, people: null })
  })

  it('is null when the look carries nothing to show, so the generic view takes it', () => {
    expect(tool('chatterbox_look', parseLook, '{}', confirmed).view).toBeNull()
    expect(parseLook(null, parseToolResult(null))).toBeNull()
  })
})

describe('lookSummary, joinSummary, leaveSummary', () => {
  it('carries the what and count', () => {
    expect(lookSummary(tool('chatterbox_look', parseLook, '{"what":"recent","count":10}'))).toBe('look recent · 10')
    expect(lookSummary(tool('chatterbox_look', parseLook, '{"what":"who"}'))).toBe('look who')
  })

  it('falls back without a what', () => {
    expect(lookSummary(tool('chatterbox_look', parseLook, null))).toBe('')
  })

  it('names the joined channel', () => {
    expect(joinSummary(tool('chatterbox_join', null, '{"channel":"#mailchecker"}'))).toBe('join #mailchecker')
    expect(joinSummary(tool('chatterbox_join', null, '{"nick":"developer"}'))).toBe('join')
    expect(leaveSummary()).toBe('leave')
  })
})
