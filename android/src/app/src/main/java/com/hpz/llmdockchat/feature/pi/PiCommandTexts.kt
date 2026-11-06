package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.data.model.PiCommandOutcome
import com.hpz.llmdockchat.data.model.Rejection

fun outcomeMessage(outcome: PiCommandOutcome): String? = when (outcome) {
    PiCommandOutcome.Done -> null
    PiCommandOutcome.Pending -> "Sent — pi will pick it up"
    is PiCommandOutcome.Failed -> "pi could not run it (${outcome.error})"
    is PiCommandOutcome.Rejected -> when (outcome.reason) {
        Rejection.OFFLINE -> "pi is offline"
        Rejection.RATE_LIMITED -> "Too many messages — wait a minute"
        Rejection.BUSY -> "The dashboard is busy — try again"
        Rejection.INVALID_TEXT -> "Message is empty or too long"
        Rejection.OTHER -> "Could not send"
    }
}

fun runEndLabel(outcome: String, runEndTs: Long, lastStopAt: Long?): String {
    if (lastStopAt != null && runEndTs - lastStopAt in 0L..30_000L) return "stopped"
    if (outcome.isBlank()) return "run ended"
    return when (outcome) {
        "completed" -> "run completed"
        "aborted" -> "aborted"
        "error" -> "error"
        else -> "run $outcome"
    }
}
