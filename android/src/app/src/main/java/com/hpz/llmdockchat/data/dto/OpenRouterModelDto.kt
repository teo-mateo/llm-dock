package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.Serializable

/** One entry of `GET /api/chat/settings/openrouter-models`'s `current` list. */
@Serializable
data class OpenRouterModelDto(
    val id: String = "",
    val label: String = "",
)

/**
 * `GET /api/chat/settings/openrouter-models` (F03). Read-only from the phone —
 * `configured` gates whether the picker's remote group is shown at all
 * (`OPENROUTER_API_KEY` unset server-side means the list is decorative).
 */
@Serializable
data class OpenRouterModelsSettingsResponseDto(
    val configured: Boolean = false,
    val current: List<OpenRouterModelDto> = emptyList(),
)
