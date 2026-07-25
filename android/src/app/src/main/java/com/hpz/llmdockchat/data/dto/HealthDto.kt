package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class HealthDto(
    val status: String = "",
    val version: String? = null,
    val timestamp: String? = null,
    @SerialName("docker_available") val dockerAvailable: Boolean = false,
    @SerialName("nvidia_available") val nvidiaAvailable: Boolean = false,
)
