package com.hpz.llmdockchat.feature.thread

import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.appError
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** The three settings writes a thread performs, as the writer needs them. */
interface SettingsWrites {
    suspend fun setPrompt(promptId: String?): Result<Unit>
    suspend fun setMcpServers(serverIds: List<String>): Result<Unit>
    suspend fun setReasoningLevel(level: String?): Result<Unit>
    suspend fun setMainService(wireValue: String): Result<Unit>
}

/** What the screen renders: the values in play, and whether the server has them yet. */
data class SettingsSnapshot(
    val promptId: String? = null,
    val mcpServers: List<String> = emptyList(),
    val reasoningLevel: String? = null,
    val pending: Boolean = false,
    val reasoningPending: Boolean = false,
    val error: String? = null,
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
    private val onSnapshot: (SettingsSnapshot) -> Unit,
) {
    private var snapshot = SettingsSnapshot()

    private val promptLock = Mutex()
    private var latestPrompt = 0L
    private var confirmedPrompt: String? = null

    private val toolsLock = Mutex()
    private var latestTools = 0L

    private val levelLock = Mutex()
    private var latestLevel = 0L
    private var confirmedLevel: String? = null

    /**
     * Settings writes the server has not confirmed. Counted by [submit] before it
     * launches, not inside the coroutine: a Send evaluated on the same
     * main-thread turn as a toggle must already see the write, or the gate is a
     * race with a nicer name.
     */
    private var inFlight = 0

    val pending: Boolean get() = inFlight > 0

    /** Takes the values a full conversation read just returned as the confirmed ones. */
    fun seed(promptId: String?, mcpServers: List<String>, reasoningLevel: String?) {
        confirmedPrompt = promptId
        confirmedLevel = reasoningLevel
        publish(snapshot.copy(promptId = promptId, mcpServers = mcpServers, reasoningLevel = reasoningLevel))
    }

    fun selectPrompt(promptId: String?) {
        val write = ++latestPrompt
        publish(snapshot.copy(promptId = promptId, error = null))
        submit {
            promptLock.withLock {
                if (write != latestPrompt) return@withLock
                writes.setPrompt(promptId).fold(
                    onSuccess = { confirmedPrompt = promptId },
                    onFailure = { failure ->
                        if (write != latestPrompt) return@fold
                        publish(snapshot.copy(promptId = confirmedPrompt, error = failure.appError.displayMessage))
                    },
                )
            }
        }
    }

    fun toggleTool(serverId: String) {
        val previous = snapshot.mcpServers
        val next = if (serverId in previous) previous - serverId else previous + serverId
        val write = ++latestTools
        publish(snapshot.copy(mcpServers = next, error = null))
        submit {
            toolsLock.withLock {
                writes.setMcpServers(next).fold(
                    onSuccess = {},
                    onFailure = { failure ->
                        if (write != latestTools) return@fold
                        publish(snapshot.copy(mcpServers = previous, error = failure.appError.displayMessage))
                    },
                )
            }
        }
    }

    fun selectReasoningLevel(level: String?) {
        val previous = snapshot.reasoningLevel
        val write = ++latestLevel
        publish(snapshot.copy(reasoningLevel = level, reasoningPending = true, error = null))
        submit {
            levelLock.withLock {
                writes.setReasoningLevel(level).fold(
                    onSuccess = {
                        confirmedLevel = level
                        publish(snapshot.copy(reasoningPending = false))
                        onReasoningConfirmed()
                    },
                    onFailure = { failure ->
                        if (write != latestLevel) return@fold
                        publish(
                            snapshot.copy(
                                reasoningLevel = confirmedLevel ?: previous,
                                reasoningPending = false,
                                error = failure.appError.displayMessage,
                            ),
                        )
                    },
                )
            }
        }
    }

    /** Switching the model has no rollback: a success reloads, a failure reports. */
    fun switchModel(wireValue: String, onSwitched: suspend () -> Unit) {
        submit {
            writes.setMainService(wireValue).fold(
                onSuccess = { onSwitched() },
                onFailure = { failure -> publish(snapshot.copy(error = failure.appError.displayMessage)) },
            )
        }
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

    internal fun snapshotForTest(): SettingsSnapshot = snapshot

    private fun publish(next: SettingsSnapshot) {
        snapshot = next
        onSnapshot(next)
    }
}
