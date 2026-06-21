import { useState, useEffect } from 'react'
import { fetchAPI } from '../../api'
import { updateConversation } from '../../services/chat'

export default function McpToggle({ conversationId, enabledServers, onUpdate, onChange, disabled }) {
  const [available, setAvailable] = useState([])

  useEffect(() => {
    fetchAPI('/chat/mcp-servers')
      .then(data => setAvailable(data.servers || []))
      .catch(() => {})
  }, [])

  if (available.length === 0) return null

  async function toggle(serverId) {
    const current = enabledServers || []
    const next = current.includes(serverId)
      ? current.filter(s => s !== serverId)
      : [...current, serverId]
    // Controlled / in-memory mode (e.g. Ghost Chat): hand the new list to the
    // caller, persist nothing. Without onChange we fall back to the persisted
    // behavior — write mcp_servers_json on the conversation, then refetch.
    if (onChange) {
      onChange(next)
      return
    }
    await updateConversation(conversationId, { mcp_servers_json: JSON.stringify(next) })
    onUpdate?.()
  }

  return (
    <div className="flex items-center gap-2">
      {available.map(server => {
        const isOn = (enabledServers || []).includes(server.id)
        return (
          <button
            key={server.id}
            onClick={() => toggle(server.id)}
            disabled={disabled}
            className={`flex items-center gap-1.5 px-2 py-1 rounded text-[11px] border transition-colors ${
              isOn
                ? 'bg-success-subtle text-success-fg border-success hover:bg-success-subtle'
                : 'bg-surface text-fg-subtle border-border hover:bg-surface-strong hover:text-fg-muted'
            } disabled:opacity-50`}
            title={server.description}
          >
            <i className={`fa-solid ${server.icon} text-[10px]`}></i>
            <span>{server.name}</span>
            <span className={`text-[9px] ${isOn ? 'text-success-fg' : 'text-fg-faint'}`}>
              {isOn ? 'ON' : 'OFF'}
            </span>
          </button>
        )
      })}
    </div>
  )
}
