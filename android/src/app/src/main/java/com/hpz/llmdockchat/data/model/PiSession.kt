package com.hpz.llmdockchat.data.model

data class PiSession(
    val key: PiSessionKey,
    val name: String?,
    val cwd: String,
    val model: String?,
    val thinkingLevel: String?,
    val firstSeen: Long,
    val lastSeen: Long,
    val endedAt: Long?,
    val endReason: String?,
    val live: Boolean,
    val state: PiState,
    val contextPercent: Double?,
    val prompts: List<PiPrompt> = emptyList(),
) {
    val needsAnswer: Boolean
        get() = live && prompts.isNotEmpty()
}

data class PiPrompt(
    val promptId: String,
    val kind: String,
    val title: String?,
)

data class PiSessionKey(
    val sessionId: String,
    val instanceId: String,
)

enum class PiState {
    WORKING,
    IDLE,
    ENDED,
}
