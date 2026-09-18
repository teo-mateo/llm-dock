import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import ConversationView from './ConversationView'
import {
  parseRequestBody,
  prettyArguments,
  approxImageSize,
  messageContentChars,
} from './parse'

afterEach(cleanup)

function body(messages, extra = {}) {
  return JSON.stringify({ model: 'm', messages, ...extra })
}

describe('parse helpers', () => {
  it('parseRequestBody accepts only JSON objects with a messages array', () => {
    expect(parseRequestBody('{"messages": []}').ok).toBe(true)
    expect(parseRequestBody('{ not json').ok).toBe(false)
    expect(parseRequestBody('{"no_messages": 1}').ok).toBe(false)
    expect(parseRequestBody(null).ok).toBe(false)
  })

  it('prettyArguments pretty-prints JSON strings, passes objects, flags garbage', () => {
    expect(prettyArguments('{"a":1}')).toEqual({ text: '{\n  "a": 1\n}', valid: true })
    expect(prettyArguments({ a: 1 }).valid).toBe(true)
    expect(prettyArguments('not json').valid).toBe(false)
    expect(prettyArguments(null)).toEqual({ text: '', valid: true })
  })

  it('approxImageSize estimates data URLs and n/a-s everything else', () => {
    expect(approxImageSize('data:image/png;base64,AAAA')).toBe('3 B')
    expect(approxImageSize('https://example.com/a.png')).toBe('n/a')
  })

  it('messageContentChars counts strings and text parts', () => {
    expect(messageContentChars('hello')).toBe(5)
    expect(messageContentChars([{ text: 'ab' }, { type: 'image_url' }])).toBe(2)
    expect(messageContentChars(42)).toBe(0)
  })
})

describe('ConversationView', () => {
  it('renders the one-line summary', () => {
    render(
      <ConversationView
        requestBody={body([{ role: 'user', content: 'hi' }], { tools: [{ function: { name: 'f' } }] })}
      />
    )
    expect(screen.getByText('1 messages · 1 tools · 2 chars')).toBeInTheDocument()
  })

  it('renders messages in order with role chips, index and tool_call_id', () => {
    const messages = [
      { role: 'system', content: 'sys prompt' },
      { role: 'user', content: 'question' },
      { role: 'assistant', content: 'answer' },
      { role: 'tool', tool_call_id: 'call-9', content: 'tool output' },
    ]
    const { container } = render(<ConversationView requestBody={body(messages)} />)

    const chips = [...container.querySelectorAll('span')].filter((el) =>
      ['system', 'user', 'assistant', 'tool'].includes(el.textContent)
    )
    expect(chips.map((el) => el.textContent)).toEqual(['system', 'user', 'assistant', 'tool'])
    expect(screen.getByText('#4')).toBeInTheDocument()
    expect(screen.getByText('call-9')).toBeInTheDocument()
    expect(screen.getByText('sys prompt').closest('pre')).toBeInTheDocument()
  })

  it('defaults to Raw and switches to Rendered markdown per card', () => {
    render(<ConversationView requestBody={body([{ role: 'user', content: '# Title' }])} />)

    const pre = screen.getByText('# Title')
    expect(pre.tagName).toBe('PRE')

    fireEvent.click(screen.getByRole('button', { name: 'Rendered' }))
    expect(screen.getByRole('heading', { name: 'Title', level: 1 })).toBeInTheDocument()
  })

  it('collapses cards longer than 40 lines with a Show all control', () => {
    const long = Array.from({ length: 41 }, (_, i) => `l${i}`).join('\n')
    render(<ConversationView requestBody={body([{ role: 'user', content: long }])} />)

    expect(screen.getByText('Show all (41 lines)')).toBeInTheDocument()
    expect(screen.getByText(/…$/).textContent).toContain('l39')
    expect(screen.queryByText('l40', { exact: true })).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('Show all (41 lines)'))
    expect(screen.getByText('Collapse')).toBeInTheDocument()
  })

  it('never collapses the system prompt', () => {
    const long = Array.from({ length: 45 }, (_, i) => `s${i}`).join('\n')
    render(<ConversationView requestBody={body([{ role: 'system', content: long }])} />)
    expect(screen.queryByText(/Show all/)).not.toBeInTheDocument()
    expect(screen.getByText(/s44/)).toBeInTheDocument()
  })

  it('renders multimodal parts: data URLs inline, others as links with sizes', () => {
    const content = [
      { type: 'text', text: 'look' },
      { type: 'image_url', image_url: { url: 'data:image/png;base64,AAAA' } },
      { type: 'image_url', image_url: { url: 'https://x.test/img.png' } },
    ]
    render(<ConversationView requestBody={body([{ role: 'user', content }])} />)

    const img = screen.getByAltText('message attachment')
    expect(img.getAttribute('src')).toMatch(/^data:/)
    const link = screen.getByRole('link', { name: /https:\/\/x\.test\/img\.png/ })
    expect(link).toBeInTheDocument()
    expect(screen.getByText(/image · 3 B/)).toBeInTheDocument()
  })

  it('renders assistant tool_calls with pretty arguments and flags invalid JSON', () => {
    const messages = [
      {
        role: 'assistant',
        content: null,
        tool_calls: [
          { id: 'call-1', function: { name: 'search', arguments: '{"q":"hi"}' } },
          { id: 'call-2', function: { name: 'broken', arguments: 'not json' } },
        ],
      },
    ]
    render(<ConversationView requestBody={body(messages)} />)

    expect(screen.getByText('search')).toBeInTheDocument()
    expect(screen.getByText(/"q": "hi"/)).toBeInTheDocument()
    expect(screen.getByText('not valid JSON')).toBeInTheDocument()
  })

  it('shows the fallback and invokes onShowRequest for a malformed body', () => {
    const onShowRequest = vi.fn()
    render(<ConversationView requestBody="{ not json" onShowRequest={onShowRequest} />)
    expect(screen.getByText('This request has no message array.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'View raw request' }))
    expect(onShowRequest).toHaveBeenCalled()
  })
})
