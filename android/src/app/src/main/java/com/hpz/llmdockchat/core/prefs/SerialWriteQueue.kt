package com.hpz.llmdockchat.core.prefs

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch

/**
 * A one-consumer write queue: work reaches its destination in the order it was
 * posted, and a caller that is about to delete the only other copy can ask
 * whether its own write landed.
 *
 * [post] is best-effort — a failure is dropped, which is right for a value the
 * app can rebuild from user input. [confirmed] reports the failure instead.
 * [drain] says only that nothing posted before it is still queued, never that
 * those writes succeeded. Cancellation is never turned into a result.
 */
class SerialWriteQueue(scope: CoroutineScope) {

    private val writes = Channel<suspend () -> Unit>(Channel.UNLIMITED)

    init {
        scope.launch {
            for (write in writes) runCatching { write() }
        }
    }

    /** Queues [write] and returns immediately; a failure is dropped. */
    fun post(write: suspend () -> Unit) {
        writes.trySend(write)
    }

    /**
     * Queues [write] and hands back the deferred its result arrives on, so a
     * caller can post inside a lock and await outside it. [Channel.trySend]
     * never suspends, which is what makes that possible.
     */
    fun <T> postConfirmed(write: suspend () -> T): CompletableDeferred<Result<T>> {
        val done = CompletableDeferred<Result<T>>()
        writes.trySend {
            // The write runs on this queue's scope, so a cancellation it throws
            // is that write's failure, not the caller's: the deferred must be
            // completed either way or a caller awaiting it waits forever.
            try {
                done.complete(Result.success(write()))
            } catch (failure: Throwable) {
                done.complete(Result.failure(failure))
            }
        }
        return done
    }

    /** Queues [write] and waits for its own result. */
    suspend fun <T> confirmed(write: suspend () -> T): Result<T> = postConfirmed(write).await()

    /** Returns once everything posted before this call has run. */
    suspend fun drain() {
        val done = CompletableDeferred<Unit>()
        writes.send { done.complete(Unit) }
        done.await()
    }
}
