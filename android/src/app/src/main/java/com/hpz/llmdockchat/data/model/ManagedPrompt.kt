package com.hpz.llmdockchat.data.model

/** A row of `GET /api/chat/prompts` (F03-R2), ordered by [sortOrder]. */
data class ManagedPrompt(
    val id: String,
    val name: String,
    val sortOrder: Int,
    /** See [com.hpz.llmdockchat.data.dto.PromptDto] for why the text is carried. */
    val content: String = "",
)
