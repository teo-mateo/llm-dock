package com.hpz.llmdockchat.feature.thread

import com.hpz.llmdockchat.core.net.ReconnectBackoff
import com.hpz.llmdockchat.core.net.RunEvent
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.core.net.isTransient
import com.hpz.llmdockchat.data.model.ConversationDetail
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow

/**
 * Owns the attach → reattach → reconcile cycle of one run: after each
 * collection attempt it decides whether to resubscribe the same run, refetch
 * the conversation and follow whatever run that shows, or end the turn — and
 * it owns the retry policy that governs both loops.
 *
 * Everything screen-shaped (publishing frames, the reconnecting indicator,
 * settling the turn) stays behind [collectAttempt], [setReconnecting] and the
 * returned [RunSupervision]; the caller turns those into UI and calls its own
 * finish path. This class is the part that can be tested without ViewModel
 * scaffolding.
 *
 * A terminal frame ends it, a failure the server will repeat ends it, a
 * cancellation propagates — and a connection that keeps dropping is retried,
 * not surfaced, for as long as the caller keeps collecting. One thing does end
 * it: [DEFAULT_MAX_FRAMELESS_ATTEMPTS] attempts in a row that delivered no
 * frame (a dropped stream, a refused load — both count), because a server
 * that keeps failing is a verdict about the run, not an outage to wait out.
 * Any frame, or a load that answers, starts the count over — a dashboard
 * restart survives, a persistent 5xx does not.
 */
internal class RunSupervisor(
    private val reattach: suspend (String) -> Flow<RunEvent>,
    private val load: suspend () -> Result<ConversationDetail>,
    private val collectAttempt: suspend (Flow<RunEvent>, String?) -> RunAttempt,
    private val setReconnecting: (Boolean) -> Unit,
    private val backoff: ReconnectBackoff,
    private val maxFramelessAttempts: Int = DEFAULT_MAX_FRAMELESS_ATTEMPTS,
) {
    private var framelessStreak = 0

    suspend fun supervise(first: Flow<RunEvent>, initialRunId: String?): RunSupervision {
        var source: Flow<RunEvent> = first
        var runId: String? = initialRunId
        var failureMessage: String? = null
        var sawAnyFrame = false
        var error: Throwable? = null
        var refetch: Result<ConversationDetail>? = null

        while (true) {
            val attempt = collectAttempt(source, runId)
            runId = attempt.runId ?: runId
            failureMessage = attempt.failureMessage ?: failureMessage
            sawAnyFrame = sawAnyFrame || attempt.sawAnyFrame
            error = attempt.error

            if (attempt.sawAnyFrame) {
                backoff.reset()
                framelessStreak = 0
            } else {
                framelessStreak++
            }

            if (attempt.sawTerminal) break

            val id = runId
            val transient = error != null && error.appError.isTransient()
            if (transient && id != null) {
                if (framelessStreak >= maxFramelessAttempts) break
                setReconnecting(true)
                delay(backoff.next())
                source = reattach(id)
                continue
            }
            if (error == null) {
                setReconnecting(true)
                val reconciled = reconcile()
                val conversation = reconciled.getOrNull()
                if (conversation == null) {
                    refetch = reconciled
                    break
                }
                val active = conversation.activeRun?.takeIf { conversation.isGenerating }
                if (active == null) {
                    refetch = reconciled
                    break
                }
                runId = active.id
                source = reattach(active.id)
                continue
            }
            break
        }

        return RunSupervision(
            error = error,
            failureMessage = failureMessage,
            sawAnyFrame = sawAnyFrame,
            refetch = refetch,
        )
    }

    /**
     * A close without a terminal frame is the transport's verdict, not the run's:
     * a proxy or a server restart drops a healthy observer, and a cancel closes
     * the stream with no frame at all. Only the run's own status settles it, so
     * the conversation is refetched — and a server that cannot answer keeps the
     * turn *not done* rather than making it done, retrying on the same capped
     * backoff that governs reattachment, until the frameless ceiling ends the
     * wait with the load's own error.
     *
     * A failure the server will repeat (a deleted conversation, an unreadable
     * body) is returned instead of retried, so the caller can end the turn.
     */
    private suspend fun reconcile(): Result<ConversationDetail> {
        while (true) {
            val result = load()
            val error = result.exceptionOrNull()?.appError
            if (error == null) {
                framelessStreak = 0
                return result
            }
            if (!error.isTransient()) return result
            if (++framelessStreak >= maxFramelessAttempts) return result
            delay(backoff.next())
        }
    }

    companion object {
        /**
         * How many attempts in a row may deliver nothing before the turn is
         * ended with the error it has. At the production backoff (1 s doubling
         * to 8 s) this is roughly 45 s of trying — long enough that a dashboard
         * restart recovers on its own, short enough that a server bug does not
         * hold the thread hostage behind a spinner that cannot resolve.
         */
        const val DEFAULT_MAX_FRAMELESS_ATTEMPTS = 8
    }
}

internal class RunSupervision(
    val error: Throwable?,
    val failureMessage: String?,
    val sawAnyFrame: Boolean,
    val refetch: Result<ConversationDetail>?,
)

internal class RunAttempt(
    val error: Throwable?,
    val runId: String?,
    val failureMessage: String?,
    val sawAnyFrame: Boolean,
    val sawTerminal: Boolean,
)
