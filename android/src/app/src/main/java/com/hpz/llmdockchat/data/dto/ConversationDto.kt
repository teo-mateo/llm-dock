package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * The trimmed shape embedded in list payloads (`Conversation.active_run_dict()`
 * server-side) — never carries `error`, unlike a single-conversation load's
 * `last_run`. The server only ever attaches a run whose status is `queued` or
 * `running` (`chat/db.py:_attach_active_runs`, `chat/runs.py:ACTIVE_STATUSES`),
 * but the mapper re-checks `status` anyway rather than trusting presence alone
 * (Architecture D2's "never trust an unrecognised value" posture).
 */
@Serializable
data class ActiveRunDto(
    val id: String? = null,
    val status: String? = null,
    @SerialName("active_step") val activeStep: String? = null,
    @SerialName("started_at") val startedAt: String? = null,
)

/** One row of `GET /api/chat/conversations`. Only the fields F02 renders. */
@Serializable
data class ConversationDto(
    val id: String = "",
    val title: String = "",
    @SerialName("main_service") val mainService: String = "",
    @SerialName("updated_at") val updatedAt: String? = null,
    @SerialName("active_run") val activeRun: ActiveRunDto? = null,
)

@Serializable
data class ConversationListResponseDto(
    val conversations: List<ConversationDto> = emptyList(),
    val total: Int = 0,
)

/** `DELETE /api/chat/conversations/<id>` → `{"ok": true}`. */
@Serializable
data class OkResponseDto(val ok: Boolean = false)

/** `POST /api/chat/conversations/delete` request body. */
@Serializable
data class DeleteConversationsRequestDto(val ids: List<String>)

/** `POST /api/chat/conversations/delete` → `{"ok": true, "deleted": <n>}`. */
@Serializable
data class DeleteConversationsResponseDto(val ok: Boolean = false, val deleted: Int = 0)

/**
 * `POST /api/chat/conversations` request body (F03-R1). [ApiJson] has
 * `explicitNulls = false` and default `encodeDefaults = false`, so a null
 * [promptId] and null [mainSystemPrompt] are both omitted from the wire —
 * not sent as `null`. That distinction is load-bearing: with neither field
 * present, `create_conversation` in `dashboard/chat/routes.py` falls back to
 * the server's configured default system prompt (F03-R2); sending an
 * explicit null or empty string would not.
 */
@Serializable
data class CreateConversationRequestDto(
    @SerialName("main_service") val mainService: String,
    @SerialName("prompt_id") val promptId: String? = null,
    @SerialName("main_system_prompt") val mainSystemPrompt: String? = null,
)

/**
 * Only what F03 needs out of `POST`/`PUT /api/chat/conversations(/<id>)`'s
 * response — the server returns the full conversation
 * (`to_dict(include_messages=True)` on create, `to_dict()` on update); the
 * rest is ignored via `ignoreUnknownKeys`.
 */
@Serializable
data class ConversationIdResponseDto(val id: String = "")

/**
 * `PUT /api/chat/conversations/<id>` body for setting a fresh thread's tools
 * (F03-R3). `POST /api/chat/conversations` does not accept `mcp_servers_json`
 * at all — `create_conversation` builds the row from a fixed field set that
 * excludes it — so tool selection on a brand-new thread is always this
 * follow-up PUT, the same call F08 uses to change it later.
 */
@Serializable
data class UpdateMcpServersRequestDto(@SerialName("mcp_servers_json") val mcpServersJson: String)

/**
 * `PUT /api/chat/conversations/<id>` body for switching a thread's model
 * mid-conversation (F07-R4). Earlier messages are untouched — each already
 * carries its own `model_service` — only the next turn is affected.
 */
@Serializable
data class UpdateMainServiceRequestDto(@SerialName("main_service") val mainService: String)

/** `PUT /api/chat/conversations/<id>` body for a prompt change. */
@Serializable
data class UpdateSystemPromptRequestDto(
    @SerialName("main_system_prompt") val mainSystemPrompt: String,
)
