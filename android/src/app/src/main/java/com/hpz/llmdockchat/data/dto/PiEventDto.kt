package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

@Serializable
data class PiEventDto(
    val seq: Long,
    val type: String,
    val ts: Long,
    val payload: JsonObject,
)
