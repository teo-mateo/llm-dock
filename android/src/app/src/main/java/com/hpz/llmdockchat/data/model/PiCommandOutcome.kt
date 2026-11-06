package com.hpz.llmdockchat.data.model

sealed interface PiCommandOutcome {
    data object Done : PiCommandOutcome
    data object Pending : PiCommandOutcome
    data class Failed(val error: String?) : PiCommandOutcome
    data class Rejected(val reason: Rejection) : PiCommandOutcome
}

enum class Rejection {
    OFFLINE,
    RATE_LIMITED,
    BUSY,
    INVALID_TEXT,
    OTHER,
}
