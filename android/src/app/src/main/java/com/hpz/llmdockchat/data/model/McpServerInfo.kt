package com.hpz.llmdockchat.data.model

/** A row of `GET /api/chat/mcp-servers` (F03-R3, F08). */
data class McpServerInfo(val id: String, val name: String, val description: String, val icon: String)
