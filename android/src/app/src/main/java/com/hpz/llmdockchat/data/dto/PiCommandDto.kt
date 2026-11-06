package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class PiCommandResponseDto(
    @SerialName("command_id") val commandId: String? = null,
    val ok: Boolean? = null,
    val error: String? = null,
    val pending: Boolean? = null,
)

@Serializable
data class PiMessageRequestDto(val text: String)
