package com.hpz.llmdockchat.data.model

import kotlinx.serialization.json.JsonObject

data class PiEvent(
    val seq: Long,
    val type: String,
    val ts: Long,
    val payload: JsonObject,
)
