package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class ProviderModelDto(
    val id: String = "",
    val label: String = "",
    val vision: Boolean = false,
    val tools: Boolean = false,
    @SerialName("context_length") val contextLength: Long? = null,
)

@Serializable
data class ProviderModelsRowDto(
    val id: String = "",
    val name: String = "",
    val configured: Boolean = false,
    val models: List<ProviderModelDto> = emptyList(),
    val stale: Boolean = false,
    val error: String? = null,
)

@Serializable
data class ProviderModelsResponseDto(
    val providers: List<ProviderModelsRowDto> = emptyList(),
)
