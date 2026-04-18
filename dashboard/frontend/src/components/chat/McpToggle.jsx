import { useState, useEffect } from 'react'
import { fetchAPI } from '../../api'
import { updateConversation } from '../../services/chat'

export default function McpToggle({ conversationId, enabledServers, onUpdate, disabled }) {
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
                ? 'bg-green-600/20 text-green-400 border-green-600/40 hover:bg-green-600/30'
                : 'bg-gray-800 text-gray-500 border-gray-700 hover:bg-gray-700 hover:text-gray-400'
            } disabled:opacity-50`}
            title={server.description}
          >
            <i className={`fa-solid ${server.icon} text-[10px]`}></i>
            <span>{server.name}</span>
            <span className={`text-[9px] ${isOn ? 'text-green-500' : 'text-gray-600'}`}>
              {isOn ? 'ON' : 'OFF'}
            </span>
          </button>
        )
      })}
    </div>
  )
}
