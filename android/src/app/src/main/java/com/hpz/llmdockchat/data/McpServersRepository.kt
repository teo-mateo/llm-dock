package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.apiCall
import com.hpz.llmdockchat.data.dto.McpServersResponseDto
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.McpServerInfo

/** `GET /api/chat/mcp-servers` (F03-R3, F08). The registry itself is edited
 * from the dashboard's Tools page only — this is a read of what's enabled. */
class McpServersRepository(private val api: ApiClient) {
    suspend fun list(): Result<List<McpServerInfo>> = apiCall {
        api.get(Endpoints.MCP_SERVERS, McpServersResponseDto.serializer()).servers.map { it.toDomain() }
    }
}
