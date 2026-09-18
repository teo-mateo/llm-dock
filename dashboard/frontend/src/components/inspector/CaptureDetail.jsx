import { useState } from 'react'
import CopyablePre from '../chat/CopyablePre'
import ConversationView, { StringContent, ToolCallBlock } from './ConversationView'
import { parseRequestBody, formatDuration, formatAbsolute, copyText } from './parse'

const TABS = ['conversation', 'tools', 'request', 'response', 'meta']

function TruncationBanner({ text }) {
  return (
    <div className="mb-3 px-3 py-2 rounded border border-warning-fg/40 bg-warning-subtle text-warning-fg text-xs">
      <i className="fa-solid fa-triangle-exclamation mr-2"></i>{text}
    </div>
  )
}

function ToolDefBlock({ tool, open, onToggle }) {
  const fn = tool?.function || tool || {}
  const name = fn.name || '(unnamed)'
  return (
    <details
      className="rounded border border-border"
      open={open}
      onToggle={(e) => onToggle(e.target.open)}
    >
      <summary className="px-3 py-2 cursor-pointer text-sm font-mono text-xs">{name}</summary>
      <div className="px-3 pb-3">
        {fn.description && <p className="text-xs text-fg-muted mb-2">{fn.description}</p>}
        {fn.parameters != null && (
          <CopyablePre>{JSON.stringify(fn.parameters, null, 2)}</CopyablePre>
        )}
      </div>
    </details>
  )
}

function RequestTab({ capture, body }) {
  const fields = body
    ? Object.entries(body).filter(([key]) => key !== 'messages' && key !== 'tools')
    : []
  return (
    <div>
      {capture.request_truncated && (
        <TruncationBanner text="Request body was truncated at 1 MB." />
      )}
      {!body && (
        <p className="text-sm text-fg-muted mb-3">Request body is not JSON. Raw text below.</p>
      )}
      {fields.length > 0 && (
        <table className="w-full text-xs mb-4">
          <tbody>
            {fields.map(([key, value]) => (
              <tr key={key} className="border-b border-border-subtle">
                <td className="py-1.5 pr-4 font-mono text-fg-muted align-top whitespace-nowrap">{key}</td>
                <td className="py-1.5 text-fg">
                  {typeof value === 'object' && value !== null ? (
                    <pre className="font-mono whitespace-pre-wrap break-words">{JSON.stringify(value, null, 2)}</pre>
                  ) : String(value)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3 className="text-xs font-medium text-fg-muted mb-1">Raw request body</h3>
      <CopyablePre className="font-mono text-xs whitespace-pre-wrap break-words bg-surface-muted rounded p-3 max-h-[32rem] overflow-auto">
        {capture.request_body ?? ''}
      </CopyablePre>
    </div>
  )
}

function ResponseTab({ capture }) {
  const toolCalls = Array.isArray(capture.tool_calls) ? capture.tool_calls : []
  return (
    <div>
      {capture.response_truncated && (
        <TruncationBanner text="Response body was truncated at 1 MB." />
      )}
      {capture.finish_reason && (
        <span className="inline-block mb-3 px-2 py-0.5 rounded text-xs font-medium bg-badge-neutral-bg text-badge-neutral-fg">
          {capture.finish_reason}
        </span>
      )}
      {capture.reasoning_text && (
        <details className="mb-3 rounded border border-border">
          <summary className="px-3 py-2 cursor-pointer text-sm text-fg-muted">
            <i className="fa-solid fa-brain mr-2"></i>Thinking
          </summary>
          <div className="px-3 pb-2">
            <pre className="font-mono text-xs whitespace-pre-wrap break-words bg-surface-muted rounded p-3 max-h-96 overflow-auto">
              {capture.reasoning_text}
            </pre>
          </div>
        </details>
      )}
      {typeof capture.response_text === 'string' && capture.response_text !== '' && (
        <StringContent text={capture.response_text} defaultMode="rendered" />
      )}
      {toolCalls.map((call, i) => (
        <ToolCallBlock key={call?.id || i} call={call} />
      ))}
      <details className="mt-3 rounded border border-border">
        <summary className="px-3 py-2 cursor-pointer text-sm text-fg-muted">
          <i className="fa-solid fa-code mr-2"></i>Raw response
        </summary>
        <div className="px-3 pb-2">
          <CopyablePre className="font-mono text-xs whitespace-pre-wrap break-words bg-surface-muted rounded p-3 max-h-96 overflow-auto">
            {capture.response_body ?? ''}
          </CopyablePre>
        </div>
      </details>
    </div>
  )
}

function MetaTab({ capture }) {
  const headers = capture.request_headers && typeof capture.request_headers === 'object'
    ? Object.entries(capture.request_headers)
    : []
  const rows = [
    ['Service', capture.service_name],
    ['Model', capture.model],
    ['Template type', capture.template_type],
    ['Method', capture.method],
    ['Path', capture.path],
    ['Status', capture.status_code != null ? String(capture.status_code) : '—'],
    ['Stream', capture.stream ? 'yes' : 'no'],
    ['TTFB', capture.ttfb_ms != null ? formatDuration(capture.ttfb_ms) : '—'],
    ['Duration', capture.duration_ms != null ? formatDuration(capture.duration_ms) : '—'],
    ['Prompt tokens', capture.prompt_tokens != null ? String(capture.prompt_tokens) : '—'],
    ['Completion tokens', capture.completion_tokens != null ? String(capture.completion_tokens) : '—'],
    ['Total tokens', capture.total_tokens != null ? String(capture.total_tokens) : '—'],
    ['Created at', formatAbsolute(capture.created_at)],
    ['Error', capture.error || '—'],
    ['Request truncated', capture.request_truncated ? 'yes' : 'no'],
    ['Response truncated', capture.response_truncated ? 'yes' : 'no'],
    ['Capture id', capture.id],
  ]
  return (
    <div>
      <dl className="text-sm grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 mb-6">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-fg-subtle">{label}</dt>
            <dd className="text-fg font-mono text-xs break-all">{value ?? '—'}</dd>
          </div>
        ))}
      </dl>
      <h3 className="text-xs font-medium text-fg-muted mb-2">Request headers</h3>
      <table className="w-full text-xs">
        <tbody>
          {headers.map(([key, value]) => (
            <tr key={key} className="border-b border-border-subtle">
              <td className="py-1.5 pr-4 font-mono text-fg-muted align-top whitespace-nowrap">{key}</td>
              <td className="py-1.5 font-mono text-fg break-all">{value}</td>
            </tr>
          ))}
          {headers.length === 0 && (
            <tr><td className="py-1.5 text-fg-subtle">No headers captured.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function ToolsTab({ tools }) {
  const [openSet, setOpenSet] = useState(() => new Set())
  const openAll = () => setOpenSet(new Set(tools.map((_, i) => i)))
  const closeAll = () => setOpenSet(new Set())
  const toggle = (index, open) => {
    setOpenSet((prev) => {
      const next = new Set(prev)
      if (open) next.add(index)
      else next.delete(index)
      return next
    })
  }

  if (!tools || tools.length === 0) {
    return <p className="text-sm text-fg-muted">No tools were sent with this request.</p>
  }

  return (
    <div>
      <div className="flex gap-3 mb-3 text-xs">
        <button
          type="button"
          onClick={openAll}
          className="px-2 py-1 rounded border border-border text-fg-muted hover:text-fg cursor-pointer"
        >
          Expand all
        </button>
        <button
          type="button"
          onClick={closeAll}
          className="px-2 py-1 rounded border border-border text-fg-muted hover:text-fg cursor-pointer"
        >
          Collapse all
        </button>
      </div>
      <div className="space-y-2">
        {tools.map((tool, i) => (
          <ToolDefBlock key={i} tool={tool} open={openSet.has(i)} onToggle={(o) => toggle(i, o)} />
        ))}
      </div>
    </div>
  )
}

export default function CaptureDetail({ capture, onDelete, onConfirmStateChange }) {
  const [tab, setTab] = useState('conversation')
  const [confirming, setConfirming] = useState(false)
  const [copied, setCopied] = useState(false)

  const parsed = parseRequestBody(capture.request_body)
  const body = parsed.ok ? parsed.body : null
  const tools = body && Array.isArray(body.tools) ? body.tools : []
  const statusLabel = capture.status_code != null
    ? String(capture.status_code)
    : capture.error ? 'error' : '—'

  const setConfirm = (value) => {
    setConfirming(value)
    if (onConfirmStateChange) onConfirmStateChange(value)
  }

  const handleDelete = () => {
    setConfirm(false)
    onDelete(capture.id)
  }

  const handleCopyRequest = async () => {
    if (await copyText(capture.request_body ?? '')) {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
  }

  const tabClass = (name) => `pb-3 text-sm font-medium cursor-pointer ${
    tab === name ? 'border-b-2 border-accent text-fg' : 'text-fg-muted hover:text-fg'
  }`

  return (
    <div>
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="min-w-0">
          <h2 className="font-mono text-base text-fg truncate" title={capture.model || ''}>
            {capture.model || '—'}
          </h2>
          <p className="text-xs text-fg-subtle mt-1 break-words">
            {capture.service_name} · {capture.method} {capture.path} · {statusLabel}
            {capture.duration_ms != null && ` · ${formatDuration(capture.duration_ms)}`}
            {` · ${formatAbsolute(capture.created_at)}`}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {confirming ? (
            <>
              <button
                type="button"
                onClick={handleDelete}
                className="px-2 py-1 rounded bg-danger text-white text-xs font-medium cursor-pointer"
              >
                Delete?
              </button>
              <button
                type="button"
                onClick={() => setConfirm(false)}
                className="px-2 py-1 rounded border border-border text-fg-muted hover:text-fg text-xs cursor-pointer"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => setConfirm(true)}
                className="px-2 py-1 rounded border border-danger text-danger-fg hover:bg-danger-subtle text-xs cursor-pointer"
              >
                <i className="fa-solid fa-trash-can mr-1"></i>Delete
              </button>
              <button
                type="button"
                onClick={handleCopyRequest}
                className="px-2 py-1 rounded border border-border text-fg-muted hover:text-fg text-xs cursor-pointer"
              >
                <i className={`fa-solid ${copied ? 'fa-check' : 'fa-copy'} mr-1`}></i>
                {copied ? 'Copied' : 'Copy request JSON'}
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex gap-6 border-b border-border mb-6">
        <button type="button" onClick={() => setTab('conversation')} className={tabClass('conversation')}>
          Conversation
        </button>
        <button type="button" onClick={() => setTab('tools')} className={tabClass('tools')}>
          Tools
          {tools.length > 0 && (
            <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-medium bg-badge-neutral-bg text-badge-neutral-fg">
              {tools.length}
            </span>
          )}
        </button>
        <button type="button" onClick={() => setTab('request')} className={tabClass('request')}>
          Request
        </button>
        <button type="button" onClick={() => setTab('response')} className={tabClass('response')}>
          Response
        </button>
        <button type="button" onClick={() => setTab('meta')} className={tabClass('meta')}>
          Meta
        </button>
      </div>

      {tab === 'conversation' && (
        <ConversationView
          requestBody={capture.request_body}
          onShowRequest={() => setTab('request')}
        />
      )}
      {tab === 'tools' && <ToolsTab tools={tools} />}
      {tab === 'request' && <RequestTab capture={capture} body={body} />}
      {tab === 'response' && <ResponseTab capture={capture} />}
      {tab === 'meta' && <MetaTab capture={capture} />}
    </div>
  )
}
