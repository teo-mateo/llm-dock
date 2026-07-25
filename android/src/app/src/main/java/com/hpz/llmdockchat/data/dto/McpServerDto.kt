package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.Serializable

/** One row of `GET /api/chat/mcp-servers` (F03-R3). */
@Serializable
data class McpServerDto(
    val id: String = "",
    val name: String = "",
    val description: String = "",
    val icon: String = "",
)

@Serializable
data class McpServersResponseDto(val servers: List<McpServerDto> = emptyList())
