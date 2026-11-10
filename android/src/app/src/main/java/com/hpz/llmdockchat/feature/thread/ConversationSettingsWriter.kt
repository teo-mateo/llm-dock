package com.hpz.llmdockchat.feature.thread

import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.appError
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** The settings writes a thread performs, as the writer needs them. */
interface SettingsWrites {
    suspend fun setPrompt(promptId: String?): Result<Unit>
    suspend fun setMcpServers(serverIds: List<String>): Result<Unit>
    suspend fun setReasoningLevel(level: String?): Result<Unit>
}

/**
 * The values in play and whether the server has them yet. A failure is not here:
 * it is an event, delivered once through the writer's error callback, so a
 * banner the user dismissed cannot come back on the next publish.
 */
data class SettingsSnapshot(
    val promptId: String? = null,
    val mcpServers: List<String> = emptyList(),
    val reasoningLevel: String? = null,
    val pending: Boolean = false,
    val reasoningPending: Boolean = false,
)

/**
 * Owns the conversation-settings writes: per-setting serialization, the newest
 * write winning, rollback to the last confirmed value, and the count of writes
 * the server has not confirmed.
 *
 * The values live here rather than in the screen state so that ordering is a
 * property of this class, testable with a fake [SettingsWrites] and no HTTP.
 */
class ConversationSettingsWriter(
    private val writes: SettingsWrites,
    private val scope: CoroutineScope,
    private val onReasoningConfirmed: () -> Unit = {},
    private val onError: (String) -> Unit = {},
    private val onSnapshot: (SettingsSnapshot) -> Unit,
) {
    private var snapshot = SettingsSnapshot()

    private val promptLock = Mutex()
    private var latestPrompt = 0L
    private var confirmedPrompt: String? = null
    private var promptOutstanding = 0

    private val toolsLock = Mutex()
    private var latestTools = 0L
    private var confirmedTools: List<String> = emptyList()
    private var toolsOutstanding = 0

    private val levelLock = Mutex()
    private var latestLevel = 0L
    private var confirmedLevel: String? = null
    private var levelOutstanding = 0

    /**
     * Settings writes the server has not confirmed. Counted by [submit] before it
     * launches, not inside the coroutine: a Send evaluated on the same
     * main-thread turn as a toggle must already see the write, or the gate is a
     * race with a nicer name.
     */
    private var inFlight = 0

    val pending: Boolean get() = inFlight > 0

    val current: SettingsSnapshot get() = snapshot

    /**
     * Takes the values a full conversation read returned as the confirmed ones.
     * A setting with a write outstanding keeps the value the user chose: the
     * server's copy of it is older than the write in flight.
     */
    fun seed(promptId: String?, mcpServers: List<String>, reasoningLevel: String?) {
        confirmedPrompt = promptId
        confirmedTools = mcpServers
        confirmedLevel = reasoningLevel
        publish(
            snapshot.copy(
                promptId = if (promptOutstanding > 0) snapshot.promptId else promptId,
                mcpServers = if (toolsOutstanding > 0) snapshot.mcpServers else mcpServers,
                reasoningLevel = if (levelOutstanding > 0) snapshot.reasoningLevel else reasoningLevel,
            ),
        )
    }

    fun selectPrompt(promptId: String?) {
        val write = ++latestPrompt
        promptOutstanding++
        publish(snapshot.copy(promptId = promptId))
        submit {
            try {
                promptLock.withLock {
                    if (write != latestPrompt) return@withLock
                    writes.setPrompt(promptId).fold(
                        onSuccess = { confirmedPrompt = promptId },
                        onFailure = { failure ->
                            if (write != latestPrompt) return@fold
                            publish(snapshot.copy(promptId = confirmedPrompt))
                            onError(failure.appError.displayMessage)
                        },
                    )
                }
            } finally {
                promptOutstanding--
            }
        }
    }

    fun toggleTool(serverId: String) {
        val previous = snapshot.mcpServers
        val next = if (serverId in previous) previous - serverId else previous + serverId
        val write = ++latestTools
        toolsOutstanding++
        publish(snapshot.copy(mcpServers = next))
        submit {
            try {
                toolsLock.withLock {
                    writes.setMcpServers(next).fold(
                        onSuccess = { confirmedTools = next },
                        onFailure = { failure ->
                            if (write != latestTools) return@fold
                            publish(snapshot.copy(mcpServers = confirmedTools))
                            onError(failure.appError.displayMessage)
                        },
                    )
                }
            } finally {
                toolsOutstanding--
            }
        }
    }

    fun selectReasoningLevel(level: String?) {
        val write = ++latestLevel
        levelOutstanding++
        publish(snapshot.copy(reasoningLevel = level, reasoningPending = true))
        submit {
            try {
                levelLock.withLock {
                    writes.setReasoningLevel(level).fold(
                        onSuccess = {
                            confirmedLevel = level
                            if (write == latestLevel) {
                                publish(snapshot.copy(reasoningPending = false))
                                onReasoningConfirmed()
                        }
                    },
                    onFailure = { failure ->
                        if (write != latestLevel) return@fold
                        publish(snapshot.copy(reasoningLevel = confirmedLevel, reasoningPending = false))
                        onError(failure.appError.displayMessage)
                    },
                )
                }
            } finally {
                levelOutstanding--
            }
        }
    }

    /** Runs [block] under the same in-flight accounting, for a write that has no rollback of its own. */
    fun guard(block: suspend () -> Unit) {
        submit(block)
    }

    private fun submit(block: suspend () -> Unit) {
        inFlight++
        publish(snapshot.copy(pending = true))
        scope.launch {
            try {
                block()
            } finally {
                inFlight--
                publish(snapshot.copy(pending = inFlight > 0))
            }
        }
    }

    private fun publish(next: SettingsSnapshot) {
        snapshot = next
        onSnapshot(next)
    }
}
