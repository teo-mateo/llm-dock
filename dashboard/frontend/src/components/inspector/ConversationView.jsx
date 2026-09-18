import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import useProseClass from '../../hooks/useProseClass'
import CopyablePre from '../chat/CopyablePre'
import {
  parseRequestBody,
  prettyArguments,
  messageContentChars,
  approxImageSize,
  copyText,
} from './parse'

const MAX_VISIBLE_LINES = 40

// Categorical badge tokens: themed in both themes, mapped to the role hues
// (system violet, user blue, assistant green, tool amber).
const ROLE_CHIP = {
  system: 'bg-badge-vllm-bg text-badge-vllm-fg',
  user: 'bg-badge-llamacpp-bg text-badge-llamacpp-fg',
  assistant: 'bg-badge-webui-bg text-badge-webui-fg',
  tool: 'bg-badge-ds4-bg text-badge-ds4-fg',
}
const DEFAULT_CHIP = 'bg-badge-neutral-bg text-badge-neutral-fg'

export function StringContent({ text, defaultMode = 'raw' }) {
  const [mode, setMode] = useState(defaultMode)
  const proseClass = useProseClass('prose-sm', 'max-w-none', 'my-0')

  return (
    <div>
      <div className="flex justify-end mb-1">
        <button
          type="button"
          onClick={() => setMode(mode === 'raw' ? 'rendered' : 'raw')}
          className="text-xs px-2 py-0.5 rounded border border-border text-fg-muted hover:text-fg cursor-pointer"
        >
          {mode === 'raw' ? 'Rendered' : 'Raw'}
        </button>
      </div>
      {mode === 'raw' ? (
        <pre className="font-mono text-xs whitespace-pre-wrap break-words bg-surface-muted rounded p-3 max-h-96 overflow-auto">
          {text}
        </pre>
      ) : (
        <div className={proseClass}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      )}
    </div>
  )
}

export function ToolCallBlock({ call }) {
  const args = prettyArguments(call?.function?.arguments)
  return (
    <details className="mt-2 rounded border border-border">
      <summary className="px-3 py-2 cursor-pointer text-sm">
        <i className="fa-solid fa-wrench mr-2 text-fg-muted"></i>
        <span className="font-mono text-xs">{call?.function?.name || '(unknown)'}</span>
        {call?.id && <span className="ml-2 font-mono text-[10px] text-fg-subtle">{call.id}</span>}
      </summary>
      <div className="px-3 pb-2">
        {!args.valid && (
          <span className="inline-block mb-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-warning-subtle text-warning-fg">
            not valid JSON
          </span>
        )}
        <CopyablePre>{args.text}</CopyablePre>
      </div>
    </details>
  )
}

function ImagePart({ part }) {
  const url = part?.image_url?.url
  const size = approxImageSize(url)
  return (
    <div className="mt-2">
      {typeof url === 'string' && url.startsWith('data:') ? (
        <img src={url} alt="message attachment" className="max-h-48 rounded border border-border" />
      ) : (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent-fg hover:text-accent-fg-hover hover:underline break-all text-xs"
        >
          <i className="fa-solid fa-image mr-1"></i>{url}
        </a>
      )}
      <p className="text-[10px] text-fg-subtle mt-0.5">image · {size}</p>
    </div>
  )
}

function MessageCard({ message, index }) {
  const [copied, setCopied] = useState(false)
  const role = message?.role || 'unknown'
  const chipClass = ROLE_CHIP[role] || DEFAULT_CHIP

  const textContent = typeof message?.content === 'string'
    ? message.content
    : Array.isArray(message?.content)
      ? message.content.filter((p) => typeof p?.text === 'string').map((p) => p.text).join('\n')
      : ''
  const isMultimodal = Array.isArray(message?.content)
  const lines = textContent.split('\n').length
  const collapsible = lines > MAX_VISIBLE_LINES && role !== 'system'
  const [expanded, setExpanded] = useState(!collapsible)

  const handleCopy = async () => {
    if (await copyText(textContent)) {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
  }

  const shownText = expanded ? textContent : `${textContent.split('\n').slice(0, MAX_VISIBLE_LINES).join('\n')}\n…`

  return (
    <div className="bg-surface rounded-lg border border-border p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${chipClass}`}>{role}</span>
        <span className="text-xs text-fg-subtle">#{index}</span>
        {role === 'tool' && message.tool_call_id && (
          <span className="font-mono text-[10px] text-fg-subtle">{message.tool_call_id}</span>
        )}
        <div className="ml-auto">
          <button
            type="button"
            onClick={handleCopy}
            className="text-xs px-2 py-0.5 rounded border border-border text-fg-muted hover:text-fg cursor-pointer"
            title={copied ? 'Copied' : 'Copy'}
          >
            {copied ? '✓ Copied' : 'Copy'}
          </button>
        </div>
      </div>

      {isMultimodal ? (
        <div>
          <StringContent text={expanded ? textContent || '(no text)' : shownText || '(no text)'} />
          {message.content
            .filter((p) => p?.type === 'image_url' || typeof p?.image_url?.url === 'string')
            .map((p, i) => (
              <ImagePart key={i} part={p} />
            ))}
        </div>
      ) : typeof message?.content === 'string' ? (
        <div>
          <StringContent text={expanded ? message.content : shownText} />
          {collapsible && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="mt-1 text-xs text-accent-fg hover:text-accent-fg-hover cursor-pointer"
            >
              {expanded ? 'Collapse' : `Show all (${lines} lines)`}
            </button>
          )}
        </div>
      ) : message?.content != null ? (
        <pre className="font-mono text-xs whitespace-pre-wrap break-words bg-surface-muted rounded p-3">
          {JSON.stringify(message.content, null, 2)}
        </pre>
      ) : null}

      {Array.isArray(message.tool_calls) && message.tool_calls.length > 0 && (
        message.tool_calls.map((call, i) => <ToolCallBlock key={call?.id || i} call={call} />)
      )}
    </div>
  )
}

export default function ConversationView({ requestBody, onShowRequest }) {
  const parsed = parseRequestBody(requestBody)

  if (!parsed.ok) {
    return (
      <div className="text-center py-10">
        <p className="text-fg-muted text-sm">This request has no message array.</p>
        <button
          type="button"
          onClick={onShowRequest}
          className="mt-2 text-sm text-accent-fg hover:text-accent-fg-hover hover:underline cursor-pointer"
        >
          View raw request
        </button>
      </div>
    )
  }

  const messages = parsed.body.messages
  const toolCount = Array.isArray(parsed.body.tools) ? parsed.body.tools.length : 0
  const totalChars = messages.reduce((sum, m) => sum + messageContentChars(m?.content), 0)

  return (
    <div>
      <p className="text-xs text-fg-subtle mb-3">
        {messages.length} messages · {toolCount} tools · {totalChars} chars
      </p>
      <div className="space-y-3">
        {messages.map((m, i) => (
          <MessageCard key={i} message={m} index={i + 1} />
        ))}
      </div>
    </div>
  )
}
