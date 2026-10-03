package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** One URL-capable server from the `url_fetch` block of the probe. */
@Serializable
data class UrlFetchServerDto(
    val id: String = "",
    val name: String = "",
    val tools: List<String> = emptyList(),
)

/** A candidate the dashboard could not ask — configured, but not answering. */
@Serializable
data class UrlFetchFailureDto(val id: String = "", val error: String = "")

/** `url_fetch` on `GET /api/chat/mcp-servers?probe=url-fetch`. */
@Serializable
data class UrlFetchDto(
    val available: Boolean = false,
    val servers: List<UrlFetchServerDto> = emptyList(),
    val failures: List<UrlFetchFailureDto> = emptyList(),
)

/** One row of `GET /api/chat/mcp-servers`. */
@Serializable
data class McpServerDto(
    val id: String = "",
    val name: String = "",
    val description: String = "",
    val icon: String = "",
)

/**
 * `GET /api/chat/mcp-servers`. [urlFetch] is present only when
 * the request carried `probe=url-fetch`, and only when the dashboard knows the
 * capability at all — a null here means an older server, not "no tools".
 */
@Serializable
data class McpServersResponseDto(
    val servers: List<McpServerDto> = emptyList(),
    @SerialName("url_fetch") val urlFetch: UrlFetchDto? = null,
)
