import { useState } from 'react'
import { testServer } from '../../services/mcpRegistry'

function ToolRow({ serverId, tool }) {
  const [args, setArgs] = useState('{}')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  async function run() {
    setBusy(true)
    setError(null)
    setResult(null)
    let parsed
    try {
      parsed = JSON.parse(args || '{}')
    } catch (e) {
      setError(`Invalid JSON: ${e.message}`)
      setBusy(false)
      return
    }
    try {
      const res = await testServer(serverId, tool.name, parsed)
      if (!res.ok) {
        setError(res.error || 'Tool call failed')
      } else {
        setResult(res)
      }
    } catch (e) {
      setError(e.message || 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="border border-border rounded bg-app p-3 space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <div>
          <span className="font-mono text-sm text-warning-fg">{tool.name}</span>
          {tool.description && (
            <span className="ml-2 text-xs text-fg-muted">{tool.description}</span>
          )}
        </div>
        <button
          onClick={run}
          disabled={busy}
          className="text-xs px-2 py-1 rounded bg-accent-strong hover:bg-accent-hover disabled:opacity-50 text-white"
        >
          {busy ? 'Running…' : 'Run'}
        </button>
      </div>
      <textarea
        value={args}
        onChange={(e) => setArgs(e.target.value)}
        spellCheck={false}
        rows={3}
        className="w-full bg-surface-muted text-fg font-mono text-xs p-2 rounded border border-border focus:outline-none focus:border-accent"
        placeholder='{"query": "example"}'
      />
      {error && (
        <div className="text-xs text-danger-fg">
          <i className="fa-solid fa-triangle-exclamation mr-1"></i>{error}
        </div>
      )}
      {result && (
        <div className="text-xs space-y-1">
          <div className="text-success-fg">
            <i className="fa-solid fa-check mr-1"></i>Result
          </div>
          {result.artifacts && result.artifacts.length > 0 && (
            <div className="text-fg-muted">
              Artifacts: {result.artifacts.map((a, i) => (
                <span key={i} className="ml-1 font-mono">[{a.type}{a.content_size ? ` ${a.content_size}b` : ''}]</span>
              ))}
            </div>
          )}
          <pre className="bg-surface-muted border border-border rounded p-2 text-fg max-h-72 overflow-auto whitespace-pre-wrap">{result.result_text}</pre>
        </div>
      )}
    </div>
  )
}

export default function ServerTestPanel({ server }) {
  const [busy, setBusy] = useState(false)
  const [tools, setTools] = useState(null)
  const [error, setError] = useState(null)

  async function discover() {
    setBusy(true)
    setError(null)
    setTools(null)
    try {
      const res = await testServer(server.id)
      if (!res.ok) {
        setError(res.error || 'list_tools failed')
      } else {
        setTools(res.tools)
      }
    } catch (e) {
      setError(e.message || 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  if (!server.enabled) {
    return (
      <div className="text-xs text-fg-subtle italic">
        Server is disabled in config. Enable it to test.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <button
          onClick={discover}
          disabled={busy}
          className="text-xs px-3 py-1.5 rounded bg-surface hover:bg-surface-strong disabled:opacity-50"
        >
          {busy ? 'Discovering…' : 'List tools'}
        </button>
        {tools && (
          <span className="text-xs text-fg-muted">
            {tools.length} tool{tools.length === 1 ? '' : 's'}
          </span>
        )}
      </div>
      {error && (
        <div className="text-xs text-danger-fg">
          <i className="fa-solid fa-triangle-exclamation mr-1"></i>{error}
        </div>
      )}
      {tools && tools.length > 0 && (
        <div className="space-y-2">
          {tools.map((t) => (
            <ToolRow key={t.namespaced_name} serverId={server.id} tool={t} />
          ))}
        </div>
      )}
      {tools && tools.length === 0 && (
        <div className="text-xs text-fg-subtle italic">Server advertises no tools.</div>
      )}
    </div>
  )
}
