package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One row of `GET /api/chat/prompts` (F03-R2). Name-only on purpose: prompt
 * *selection* sends the id (the server resolves the content), and the sheet
 * identifies the thread's current prompt by the conversation's `prompt_id`
 * reference — neither path reads a prompt's text.
 */
@Serializable
data class PromptDto(
    val id: String = "",
    val name: String = "",
    @SerialName("sort_order") val sortOrder: Int = 0,
)

@Serializable
data class PromptListResponseDto(val prompts: List<PromptDto> = emptyList())
