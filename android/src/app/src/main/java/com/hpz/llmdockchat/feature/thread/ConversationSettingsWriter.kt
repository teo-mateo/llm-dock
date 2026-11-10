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
    private var promptBusy = false

    private val toolsLock = Mutex()
    private var latestTools = 0L
    private var confirmedTools: List<String> = emptyList()
    private var toolsBusy = false

    private val levelLock = Mutex()
    private var latestLevel = 0L
    private var confirmedLevel: String? = null
    private var levelBusy = false

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
                promptId = if (promptBusy) snapshot.promptId else promptId,
                mcpServers = if (toolsBusy) snapshot.mcpServers else mcpServers,
                reasoningLevel = if (levelBusy) snapshot.reasoningLevel else reasoningLevel,
            ),
        )
    }

    fun selectPrompt(promptId: String?) {
        val write = ++latestPrompt
        promptBusy = true
        publish(snapshot.copy(promptId = promptId))
        submit {
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
            promptBusy = false
        }
    }

    fun toggleTool(serverId: String) {
        val previous = snapshot.mcpServers
        val next = if (serverId in previous) previous - serverId else previous + serverId
        val write = ++latestTools
        toolsBusy = true
        publish(snapshot.copy(mcpServers = next))
        submit {
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
            toolsBusy = false
        }
    }

    fun selectReasoningLevel(level: String?) {
        val write = ++latestLevel
        levelBusy = true
        publish(snapshot.copy(reasoningLevel = level, reasoningPending = true))
        submit {
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
            levelBusy = false
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
