package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/** One entry of `GET /api/chat/settings/openrouter-models`'s `current` list. */
@Serializable
data class OpenRouterModelDto(
    val id: String = "",
    val label: String = "",
    /**
     * F15.1: the ladder the server derived for this model from OpenRouter's
     * `supported_efforts`. Deliberately the same wire shape as
     * [ServiceDto.reasoning_levels], so one parser covers both providers. Kept as
     * a raw [JsonElement] for the same reason `ServiceDto` keeps one: a ladder is
     * optional upstream, and `null` (never published) is not the same fact as an
     * empty list.
     */
    @SerialName("reasoning_levels") val reasoningLevels: JsonElement? = null,
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
