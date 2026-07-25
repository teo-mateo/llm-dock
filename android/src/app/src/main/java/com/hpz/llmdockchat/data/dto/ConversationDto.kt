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
