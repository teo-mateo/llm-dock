package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.data.PiSessionEventsState
import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.feature.pi.transcript.PiSessionSnapshot
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotIdentity
import com.hpz.llmdockchat.feature.pi.transcript.PiTranscript
import com.hpz.llmdockchat.feature.pi.transcript.TranscriptBuilder

sealed interface PiSessionUiState {
    data object Loading : PiSessionUiState
    data object Unknown : PiSessionUiState
    data class Loaded(
        val summary: PiSession?,
        val transcript: PiTranscript,
        val phase: PiSessionPhase,
        val failure: String? = null,
    ) : PiSessionUiState {
        val stale: Boolean get() = phase != PiSessionPhase.CONNECTED
        val commandsAvailable: Boolean get() = !stale && summary?.live == true
    }
}

enum class PiSessionPhase(val label: String) {
    CACHED_CHECKING("Cached · checking…"),
    CATCHING_UP("Catching up…"),
    CONNECTED("Connected"),
    RECONNECTING("Offline / reconnecting…"),
    FAILED("Unable to refresh"),
}

internal class PiTranscriptSession(seed: PiSessionSnapshot?, private var firstSeen: Long? = seed?.firstSeen) {
    private val builder = seed?.let { TranscriptBuilder(it.checkpoint) } ?: TranscriptBuilder()
    private var summary = seed?.summary
    private var transcript = builder.transcript()
    var lastSeq = seed?.lastSeq ?: 0L
        private set
    private var validated = false
    private var dirty = false

    fun initial(): PiSessionUiState.Loaded =
        PiSessionUiState.Loaded(summary, transcript, PiSessionPhase.CACHED_CHECKING)

    fun mismatch(update: PiSessionEventsState): Long? = update.summary?.firstSeen?.takeIf {
        update.caughtUp && firstSeen != null && firstSeen != it
    }

    fun accept(update: PiSessionEventsState): PiSessionUiState.Loaded {
        if (update.appended.isNotEmpty()) {
            update.appended.forEach { builder.apply(it) }
            lastSeq = update.lastSeq
            transcript = builder.transcript()
            dirty = true
        }
        validated = update.caughtUp && !update.stale
        if (validated) {
            if (summary != update.summary) dirty = true
            summary = update.summary
            firstSeen = summary?.firstSeen
        }
        val phase = when {
            update.stale -> PiSessionPhase.RECONNECTING
            validated -> PiSessionPhase.CONNECTED
            else -> PiSessionPhase.CATCHING_UP
        }
        return PiSessionUiState.Loaded(summary, transcript, phase)
    }

    fun checkpoint(identity: PiSnapshotIdentity, now: Long): PiSessionSnapshot? {
        val summary = summary ?: return null
        if (!validated || !dirty) return null
        dirty = false
        return PiSessionSnapshot(
            identity = identity, firstSeen = summary.firstSeen, lastSeq = lastSeq,
            savedAt = now, summary = summary, checkpoint = builder.checkpoint(),
        )
    }
}
