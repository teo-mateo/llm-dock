package com.hpz.llmdockchat.testing

import java.util.concurrent.ExecutorService
import java.util.concurrent.TimeUnit

/**
 * Quiesce the executor backing `Dispatchers.Main`, then hand it back.
 *
 * Call this *instead of* `Dispatchers.resetMain()` + `shutdownNow()` in an
 * `@After`. The original order was wrong in both halves:
 *
 * ```
 * store.clear()              // only *marks* the scope cancelled
 * Dispatchers.resetMain()    // dispatcher yanked while coroutines still unwind
 * mainExecutor.shutdownNow() // interrupts; does not wait for them to stop
 * ```
 *
 * Cancellation is cooperative and asynchronous: `store.clear()` marks the
 * scope, and every cancelled coroutine still has to be dispatched back onto
 * Main to unwind its `finally` blocks. Resetting before that finishes leaves
 * work running on the old dispatcher, and the *next* class to call
 * `Dispatchers.setMain` dies with `IllegalStateException: Dispatchers.Main is
 * used concurrently with setting it` — which then cascades into `lateinit
 * property server has not been initialized`, because that class's `@Before`
 * aborted half-way.
 *
 * The flake therefore always blamed whichever class ran *next*, never the one
 * that leaked. It reproduced about once in five full-suite runs; draining
 * alone only cut it to one in eight, which is not a fix.
 *
 * So: drain what is queued, stop accepting work, and **wait for termination**
 * before releasing Main. The executor is single-threaded and FIFO, so a
 * submitted no-op completing proves everything ahead of it has run; several
 * rounds because a `finally` may suspend and re-dispatch. No sleeps, no
 * wall-clock assertions.
 */
fun ExecutorService.quiesceAndRelease(rounds: Int = 3, timeoutSeconds: Long = 5) {
    repeat(rounds) {
        if (isShutdown) return@repeat
        runCatching { submit { }.get(timeoutSeconds, TimeUnit.SECONDS) }
    }
    shutdown()
    if (!awaitTermination(timeoutSeconds, TimeUnit.SECONDS)) shutdownNow()
}

/** Runs the queue dry without shutting the executor down — for use mid-test. */
fun ExecutorService.drainMain(rounds: Int = 1, timeoutSeconds: Long = 10) {
    repeat(rounds) {
        if (isShutdown) return@repeat
        runCatching { submit { }.get(timeoutSeconds, TimeUnit.SECONDS) }
    }
}
