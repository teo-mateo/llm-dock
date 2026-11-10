package com.hpz.llmdockchat.feature.thread

import com.hpz.llmdockchat.core.net.ReconnectBackoff
import com.hpz.llmdockchat.core.net.RunEvent
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.core.net.isTransient
import com.hpz.llmdockchat.data.model.ConversationDetail
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/**
 * Owns the attach → reattach → reconcile cycle of one run. After each
 * collection attempt [decide] picks the next step — end the turn, reattach a
 * run, or reconcile the conversation — and this class only executes it: the
 * waiting, the resubscribing, the flag writes.
 *
 * Everything screen-shaped (publishing frames, settling the turn) stays behind
 * [collectAttempt] and the returned [RunSupervision]; the caller turns those
 * into UI and calls its own finish path. The reconnecting flag is written here
 * and nowhere else: raised before a wait, cleared by the first frame of any
 * resubscribed stream. This class is the part that can be tested without
 * ViewModel scaffolding.
 *
 * A terminal frame ends the supervision, a failure the server will repeat ends
 * it, a cancellation propagates — and a connection that keeps dropping is
 * retried, not surfaced, for as long as the caller keeps collecting. One thing
 * does end it: [DEFAULT_MAX_FRAMELESS_ATTEMPTS] attempts in a row that delivered
 * no frame (a dropped stream, a refused load — both count), because a server
 * that keeps failing is a verdict about the run, not an outage to wait out. Any
 * frame, or a refetch that shows a different run now live, starts the count
 * over — a dashboard restart survives, a persistent 5xx does not. Progress
 * means a frame that shows the run advancing: a heartbeat, a delta, anything
 * except the `run_started` handshake the server resends on every subscribe, so
 * a proxy that passes only that frame and closes still counts as a miss. A
 * server that delivers real frames per connection is never cut off; that is
 * the price of never cutting off a live run.
 */
internal class RunSupervisor(
    private val reattach: suspend (String) -> Flow<RunEvent>,
    private val load: suspend () -> Result<ConversationDetail>,
    private val collectAttempt: suspend (Flow<RunEvent>, String?) -> RunAttempt,
    private val setReconnecting: (Boolean) -> Unit,
    private val backoff: ReconnectBackoff,
    private val maxFramelessAttempts: Int = DEFAULT_MAX_FRAMELESS_ATTEMPTS,
) {
    private val budget = FramelessBudget(maxFramelessAttempts)

    suspend fun supervise(first: Flow<RunEvent>, initialRunId: String?): RunSupervision {
        var source = first.clearingReconnectingOnFirstFrame()
        var runId = initialRunId
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

            when (val step = decide(attempt, runId)) {
                is Step.End -> {
                    refetch = step.refetch
                    break
                }
                is Step.Reattach -> {
                    setReconnecting(true)
                    if (step.wait) delay(backoff.next())
                    runId = step.runId
                    source = reattach(step.runId).clearingReconnectingOnFirstFrame()
                }
                Step.Reconcile -> {
                    setReconnecting(true)
                    val reconciled = reconcile()
                    when (val follow = decideAfterReconcile(attempt, runId, reconciled)) {
                        is Step.End -> {
                            refetch = follow.refetch
                            break
                        }
                        is Step.Reattach -> {
                            if (follow.wait) delay(backoff.next())
                            runId = follow.runId
                            source = reattach(follow.runId).clearingReconnectingOnFirstFrame()
                        }
                        Step.Reconcile -> Unit
                    }
                }
            }
        }

        return RunSupervision(
            error = error,
            failureMessage = failureMessage,
            sawAnyFrame = sawAnyFrame,
            refetch = refetch,
        )
    }

    private fun decide(attempt: RunAttempt, runId: String?): Step {
        if (attempt.madeProgress) {
            backoff.reset()
            budget.recordProgress()
        } else {
            budget.recordMiss()
        }
        if (attempt.sawTerminal) return Step.End()
        val error = attempt.error
        val transient = error != null && error.appError.isTransient()
        if (transient && runId != null) {
            return if (budget.exhausted) Step.End() else Step.Reattach(runId, wait = true)
        }
        if (error == null) return Step.Reconcile
        return Step.End()
    }

    /**
     * After a clean close, the refetched conversation decides what follows. A
     * different run now live is progress — the count restarts and the new run is
     * followed at once. The *same* run still live after a frameless attempt is
     * not: the server is answering but the stream is not delivering, which is
     * exactly the hot loop the ceiling exists to end, so the attempt keeps
     * counting and the resubscribe is backed off before it is tried.
     */
    private fun decideAfterReconcile(
        attempt: RunAttempt,
        runId: String?,
        reconciled: Result<ConversationDetail>,
    ): Step {
        val conversation = reconciled.getOrNull()
        if (conversation == null) return Step.End(refetch = reconciled)
        val active = conversation.activeRun?.takeIf { conversation.isGenerating }
        if (active == null) return Step.End(refetch = reconciled)
        if (active.id != runId || attempt.madeProgress) {
            backoff.reset()
            budget.recordProgress()
            return Step.Reattach(active.id, wait = false)
        }
        if (budget.exhausted) return Step.End(refetch = reconciled)
        return Step.Reattach(active.id, wait = true)
    }

    /**
     * A close without a terminal frame is the transport's verdict, not the run's:
     * a proxy or a server restart drops a healthy observer, and a cancel closes
     * the stream with no frame at all. Only the run's own status settles it, so
     * the conversation is refetched — and a server that cannot answer keeps the
     * turn *not done* rather than making it done, retrying on the same capped
     * backoff, each refused load counting against the same frameless budget.
     *
     * A failure the server will repeat (a deleted conversation, an unreadable
     * body) is returned instead of retried, so the caller can end the turn.
     */
    private suspend fun reconcile(): Result<ConversationDetail> {
        while (true) {
            val result = load()
            val error = result.exceptionOrNull()?.appError
            if (error == null || !error.isTransient()) return result
            budget.recordMiss()
            if (budget.exhausted) return result
            delay(backoff.next())
        }
    }

    private fun Flow<RunEvent>.clearingReconnectingOnFirstFrame(): Flow<RunEvent> = flow {
        var first = true
        collect { event ->
            if (first) {
                first = false
                setReconnecting(false)
            }
            emit(event)
        }
    }

    private sealed interface Step {
        data class End(val refetch: Result<ConversationDetail>? = null) : Step
        data class Reattach(val runId: String, val wait: Boolean) : Step
        data object Reconcile : Step
    }

    companion object {
        /**
         * How many attempts in a row may deliver nothing before the turn is
         * ended with the result it has. At the production backoff (1 s doubling
         * to 8 s) this is roughly 45 s of trying — long enough that a dashboard
         * restart recovers on its own, short enough that a server bug does not
         * hold the thread hostage behind a spinner that cannot resolve.
         */
        const val DEFAULT_MAX_FRAMELESS_ATTEMPTS = 8
    }
}

/**
 * The frameless-attempt count behind [RunSupervisor]'s ceiling, kept pure so the
 * boundary (exhausted at exactly [maxAttempts], reset by progress) is testable
 * without coroutines. One owner of the count: every miss and every sign of
 * progress goes through here.
 */
internal class FramelessBudget(private val maxAttempts: Int) {
    private var streak = 0

    fun recordProgress() {
        streak = 0
    }

    fun recordMiss() {
        streak++
    }

    val exhausted: Boolean
        get() = streak >= maxAttempts
}

internal class RunSupervision(
    val error: Throwable?,
    val failureMessage: String?,
    val sawAnyFrame: Boolean,
    val refetch: Result<ConversationDetail>?,
)

/**
 * One collection attempt's verdict. [sawAnyFrame] counts every frame including
 * the `run_started` handshake and feeds the early-failure rule in `finishRun`;
 * [madeProgress] counts only frames that show the run advancing and feeds the
 * frameless ceiling.
 */
internal class RunAttempt(
    val error: Throwable?,
    val runId: String?,
    val failureMessage: String?,
    val sawAnyFrame: Boolean,
    val sawTerminal: Boolean,
    val madeProgress: Boolean,
)
