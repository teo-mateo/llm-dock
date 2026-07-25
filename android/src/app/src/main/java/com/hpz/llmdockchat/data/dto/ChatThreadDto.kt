package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/**
 * One persisted message from `GET /api/chat/conversations/<id>`
 * (`chat/models.py:Message.to_dict`).
 *
 * `tool_calls`, `parse_warning` and `error` are omitted entirely when absent
 * rather than sent as null, and `arguments`/`result` are typed values rather
 * than strings — hence [JsonElement] and the mapper's rendering step.
 */
@Serializable
data class ChatMessageDto(
    val id: String = "",
    val role: String = "",
    val content: String = "",
    @SerialName("reasoning_content") val reasoningContent: String? = null,
    @SerialName("model_service") val modelService: String? = null,
    val images: List<String> = emptyList(),
    val seq: Int = 0,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("tool_calls") val toolCalls: List<ToolCallDto> = emptyList(),
    @SerialName("parse_warning") val parseWarning: ParseWarningDto? = null,
    val error: String? = null,
)

@Serializable
data class ToolCallDto(
    val name: String = "",
    val arguments: JsonElement? = null,
    val result: JsonElement? = null,
    @SerialName("server_id") val serverId: String? = null,
)

/** `{kind, snippet, description}` — `chat/llm_proxy.py:detect_format_drift`. */
@Serializable
data class ParseWarningDto(
    val kind: String? = null,
    val snippet: String? = null,
    val description: String? = null,
)

/**
 * `last_run` on a single-conversation load — the trimmed shape that, unlike
 * `active_run`, carries `error`. It is how a run that failed while the app was
 * elsewhere surfaces on reopening the thread (F04-R8).
 */
@Serializable
data class LastRunDto(
    val id: String? = null,
    val status: String? = null,
    val error: String? = null,
)

/**
 * One row of `chat/models.py:Artifact.to_dict()` — the wire key is `type`,
 * not `artifact_type` (that spelling is only used on the SSE frame, see
 * `RunEvent.Artifact`).
 */
@Serializable
data class ArtifactDto(
    val id: String = "",
    val type: String = "",
    val content: String = "",
    val title: String? = null,
    val language: String? = null,
)

/** `GET /api/chat/conversations/<id>` — `to_dict(include_messages=True)`. */
@Serializable
data class ConversationDetailDto(
    val id: String = "",
    val title: String = "",
    @SerialName("main_service") val mainService: String = "",
    @SerialName("mcp_servers") val mcpServers: List<String> = emptyList(),
    @SerialName("active_run") val activeRun: ActiveRunDto? = null,
    @SerialName("last_run") val lastRun: LastRunDto? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
    val messages: List<ChatMessageDto> = emptyList(),
    // `{message_id: [Artifact, …]}` — a sibling of `messages`, not nested
    // inside each one (`chat/routes.py`: `result["artifacts"] = …`).
    val artifacts: Map<String, List<ArtifactDto>> = emptyMap(),
)

/** `POST /api/chat/conversations/<id>/messages` body. */
@Serializable
data class SendMessageRequestDto(
    val content: String,
    val images: List<String>? = null,
)

/** `POST …/cancel-active-run` body — the guard against a stale Stop (F04-R6). */
@Serializable
data class CancelRunRequestDto(@SerialName("expected_run_id") val expectedRunId: String? = null)

/**
 * `POST …/cancel-active-run` → `{"run": <run>}` or `{"run": null}`. A null run
 * is a 200 no-op: the conversation had no active run, or its active run was not
 * the one the client meant to stop.
 */
@Serializable
data class CancelRunResponseDto(val run: LastRunDto? = null)

/** `DELETE …/messages/<id>` → `{"ok": true}` (F06). Nothing else is returned —
 *  the caller already knows which message it deleted. */
@Serializable
data class DeleteMessageResponseDto(val ok: Boolean = false)
