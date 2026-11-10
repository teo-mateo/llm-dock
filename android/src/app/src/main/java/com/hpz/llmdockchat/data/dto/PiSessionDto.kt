package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class PiSessionDto(
    @SerialName("session_id") val sessionId: String,
    @SerialName("instance_id") val instanceId: String,
    val name: String? = null,
    val cwd: String,
    val model: String? = null,
    @SerialName("thinking_level") val thinkingLevel: String? = null,
    @SerialName("first_seen") val firstSeen: Long,
    @SerialName("last_seen") val lastSeen: Long,
    @SerialName("ended_at") val endedAt: Long? = null,
    @SerialName("end_reason") val endReason: String? = null,
    val live: Boolean,
    val state: String? = null,
    @SerialName("context_percent") val contextPercent: Double? = null,
    @SerialName("parent_session_id") val parentSessionId: String? = null,
    @SerialName("parent_instance_id") val parentInstanceId: String? = null,
    val project: String? = null,
    val prompts: List<PiPromptDto> = emptyList(),
)

@Serializable
data class PiSessionDeletedResponseDto(val deleted: Boolean = false)

@Serializable
data class PiPromptDto(
    @SerialName("prompt_id") val promptId: String,
    val kind: String,
    val title: String? = null,
)
