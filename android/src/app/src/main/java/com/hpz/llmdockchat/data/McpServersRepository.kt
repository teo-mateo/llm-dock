package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.apiCall
import com.hpz.llmdockchat.data.dto.McpServersResponseDto
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.McpServerInfo
import com.hpz.llmdockchat.data.model.UrlRetrieval

/** The enabled servers, plus what the dashboard says about page fetching. */
data class McpCatalog(val servers: List<McpServerInfo>, val urlRetrieval: UrlRetrieval)

/** `GET /api/chat/mcp-servers` (F03-R3, F08). The registry itself is edited
 * from the dashboard's Tools page only — this is a read of what's enabled. */
class McpServersRepository(private val api: ApiClient) {
    suspend fun list(): Result<List<McpServerInfo>> = catalog(probe = false).map { it.servers }

    /**
     * The same read with `?probe=url-fetch` (F14-R7): which enabled servers
     * can actually fetch a URL, decided server-side from each tool's parameter
     * schema. A dashboard too old to answer the probe comes back
     * [UrlRetrieval.UNSUPPORTED] rather than empty, because "no page tool
     * exists" and "this dashboard cannot say" are different instructions to
     * give the user.
     */
    suspend fun urlFetchProbe(): Result<UrlRetrieval> = catalog(probe = true).map { it.urlRetrieval }

    suspend fun catalog(probe: Boolean = false): Result<McpCatalog> = apiCall {
        val response = api.get(
            Endpoints.MCP_SERVERS,
            McpServersResponseDto.serializer(),
            query = if (probe) mapOf(PROBE_PARAM to URL_FETCH_PROBE) else emptyMap(),
        )
        McpCatalog(
            servers = response.servers.map { it.toDomain() },
            urlRetrieval = response.urlFetch?.toDomain() ?: UrlRetrieval.UNSUPPORTED,
        )
    }

    private companion object {
        const val PROBE_PARAM = "probe"
        const val URL_FETCH_PROBE = "url-fetch"
    }
}
