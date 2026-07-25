package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** One row of `GET /api/chat/prompts` (F03-R2). [content] is not carried into the
 * domain model — the phone never shows it, only picks a prompt by name. */
@Serializable
data class PromptDto(
    val id: String = "",
    val name: String = "",
    @SerialName("sort_order") val sortOrder: Int = 0,
)

@Serializable
data class PromptListResponseDto(val prompts: List<PromptDto> = emptyList())
