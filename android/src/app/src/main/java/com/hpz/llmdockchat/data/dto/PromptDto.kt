package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One row of `GET /api/chat/prompts` (F03-R2).
 *
 * [content] is carried now, and has to be: `PUT /api/chat/conversations/<id>`
 * accepts `main_system_prompt` but not `prompt_id` (`chat/db.py`'s allowed
 * set), so switching an existing thread's prompt means sending the text. It is
 * also what identifies the thread's current prompt — the conversation stores
 * the resolved content, not which prompt it came from.
 */
@Serializable
data class PromptDto(
    val id: String = "",
    val name: String = "",
    val content: String = "",
    @SerialName("sort_order") val sortOrder: Int = 0,
)

@Serializable
data class PromptListResponseDto(val prompts: List<PromptDto> = emptyList())
