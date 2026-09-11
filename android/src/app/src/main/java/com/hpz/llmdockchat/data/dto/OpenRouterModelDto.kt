package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class OpenRouterModelDto(
    val id: String = "",
    val label: String = "",
    @SerialName("reasoning_levels") val reasoningLevels: JsonElement? = null,
)

@Serializable
data class OpenRouterModelsSettingsResponseDto(
    val configured: Boolean = false,
    val current: List<OpenRouterModelDto> = emptyList(),
)
