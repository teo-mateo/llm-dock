import { useMemo, useState } from 'react'
import useRegistry from '../../hooks/useRegistry'
import RegistryEditor from './RegistryEditor'
import DefaultPromptEditor from './DefaultPromptEditor'
import ServerTestPanel from './ServerTestPanel'

function ServerRow({ server, selected, onSelect }) {
  return (
    <button
      onClick={() => onSelect(server.id)}
      className={`w-full text-left px-3 py-2 rounded border ${
        selected
          ? 'bg-surface border-border-strong'
          : 'bg-app border-transparent hover:bg-surface-muted'
      }`}
    >
      <div className="flex items-center gap-3">
        <i className={`fa-solid ${server.icon} text-fg-muted w-4 text-center`}></i>
        <div className="flex-1 min-w-0">
          <div className="text-sm text-fg truncate">{server.name}</div>
          <div className="text-[11px] text-fg-subtle truncate">{server.description}</div>
        </div>
        {!server.enabled && (
          <span className="text-[10px] uppercase tracking-wide text-fg-subtle border border-border px-1.5 py-0.5 rounded">disabled</span>
        )}
        {server.command_exists === false && (
          <span className="text-[10px] uppercase tracking-wide text-danger-fg border border-danger px-1.5 py-0.5 rounded">no command</span>
        )}
      </div>
    </button>
  )
}

function ServerDetails({ server, registryErrors }) {
  const entryError = registryErrors?.find(e => e.entry_id === server.id)
  return (
    <div className="space-y-3">
      <div>
        <div className="flex items-center gap-3">
          <i className={`fa-solid ${server.icon} text-fg-muted`}></i>
          <h2 className="text-lg text-fg">{server.name}</h2>
          <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded border ${
            server.source === 'built-in'
              ? 'border-accent text-accent-fg-hover'
              : 'border-purple-700 text-purple-300'
          }`}>{server.source}</span>
          {!server.enabled && (
            <span className="text-[10px] uppercase tracking-wide text-fg-subtle border border-border px-1.5 py-0.5 rounded">disabled</span>
          )}
        </div>
        <p className="text-sm text-fg-muted mt-1">{server.description}</p>
      </div>

      {server.source === 'built-in' ? (
        <div className="text-xs text-fg-subtle bg-app border border-border rounded px-3 py-2">
          Built-in server. Defined in <span className="font-mono">dashboard/chat/mcp_registry.py</span>. Edit via code.
        </div>
      ) : server.transport === 'http' ? (
        <div className="bg-app border border-border rounded px-3 py-2 space-y-1 text-xs">
          <div>
            <span className="text-fg-subtle">transport:</span>{' '}
            <span className="font-mono text-fg">http</span>
          </div>
          <div>
            <span className="text-fg-subtle">url:</span>{' '}
            <span className="font-mono text-fg break-all">{server.url}</span>
          </div>
          {server.header_keys && server.header_keys.length > 0 && (
            <div>
              <span className="text-fg-subtle">headers:</span>{' '}
              <span className="font-mono text-fg">{server.header_keys.join(', ')}</span>
              <span className="text-fg-subtle"> ({server.header_keys.length}, values not shown)</span>
            </div>
          )}
        </div>
      ) : (
        <div className="bg-app border border-border rounded px-3 py-2 space-y-1 text-xs">
          <div>
            <span className="text-fg-subtle">command:</span>{' '}
            <span className="font-mono text-fg">{server.command}</span>
            {server.command_exists === false && (
              <span className="ml-2 text-danger-fg">(not found on disk)</span>
            )}
          </div>
          {server.args && server.args.length > 0 && (
            <div>
              <span className="text-fg-subtle">args:</span>{' '}
              <span className="font-mono text-fg">{server.args.join(' ')}</span>
            </div>
          )}
          {server.command_exists === false && (
            <div className="text-danger-fg mt-1">
              <i className="fa-solid fa-triangle-exclamation mr-1"></i>
              Hidden from chat until the command exists.
            </div>
          )}
        </div>
      )}

      {entryError && (
        <div className="text-xs text-danger-fg bg-danger-subtle border border-danger rounded px-3 py-2">
          <i className="fa-solid fa-triangle-exclamation mr-1"></i>
          {entryError.message}
        </div>
      )}

      <div className="pt-2 border-t border-border">
        <h3 className="text-xs uppercase tracking-wide text-fg-subtle mb-2">Test</h3>
        {/* key={server.id} forces a remount when switching servers so
            the panel's discovered-tools / result / textarea state is
            dropped — otherwise the previous server's tool list and Run
            output would linger on the new server's pane. */}
        <ServerTestPanel key={server.id} server={server} />
      </div>
    </div>
  )
}

export default function ToolsPage() {
  const { data, json, loading, error, save, reload } = useRegistry()
  const [selectedId, setSelectedId] = useState(null)

  const servers = data?.servers || []
  const grouped = useMemo(() => {
    const builtin = servers.filter(s => s.source === 'built-in')
    const external = servers.filter(s => s.source === 'external')
    return { builtin, external }
  }, [servers])

  const selected = useMemo(() => {
    if (!servers.length) return null
    return servers.find(s => s.id === selectedId) || servers[0]
  }, [servers, selectedId])

  if (loading) {
    return (
      <div className="p-6 text-fg-muted">
        <i className="fa-solid fa-spinner fa-spin mr-2"></i>Loading registry…
      </div>
    )
  }
  if (error) {
    return (
      <div className="p-6 text-danger-fg">
        <i className="fa-solid fa-triangle-exclamation mr-2"></i>{error}
      </div>
    )
  }

  return (
    <div className="space-y-4 max-w-6xl">
      <div>
        <h1 className="text-xl text-fg">Tools</h1>
        <p className="text-sm text-fg-muted">
          MCP servers available to the chat. Built-in servers ship with the dashboard; external servers are
          declared in a JSON file on disk.
        </p>
      </div>

      <DefaultPromptEditor />

      <RegistryEditor
        initialContent={json?.content}
        configPath={data?.config_file}
        externalErrors={data?.external_errors}
        loadError={data?.load_error}
        onSave={save}
        onReload={reload}
      />

      <div className="grid grid-cols-[280px_1fr] gap-4">
        <div className="space-y-3">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-fg-subtle mb-1 px-1">Built-in</div>
            <div className="space-y-1">
              {grouped.builtin.map((s) => (
                <ServerRow key={s.id} server={s} selected={selected?.id === s.id} onSelect={setSelectedId} />
              ))}
            </div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wide text-fg-subtle mb-1 px-1">External</div>
            <div className="space-y-1">
              {grouped.external.length === 0 && (
                <div className="text-xs text-fg-subtle italic px-1">None configured. Add some in the editor above.</div>
              )}
              {grouped.external.map((s) => (
                <ServerRow key={s.id} server={s} selected={selected?.id === s.id} onSelect={setSelectedId} />
              ))}
            </div>
          </div>
        </div>

        <div className="bg-surface-muted border border-border rounded p-4">
          {selected ? (
            <ServerDetails server={selected} registryErrors={data?.external_errors} />
          ) : (
            <div className="text-sm text-fg-subtle">No servers registered.</div>
          )}
        </div>
      </div>
    </div>
  )
}
