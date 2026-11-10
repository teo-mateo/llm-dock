package com.hpz.llmdockchat.feature.thread

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.core.net.ReconnectBackoff
import com.hpz.llmdockchat.data.model.ActiveRun
import com.hpz.llmdockchat.data.model.ConversationDetail
import com.hpz.llmdockchat.data.model.ModelRef
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

class RunSupervisorTest {

    private class Harness(
        attempts: List<RunAttempt>,
        loads: List<Result<ConversationDetail>> = emptyList(),
        maxFramelessAttempts: Int = RunSupervisor.DEFAULT_MAX_FRAMELESS_ATTEMPTS,
    ) {
        val remainingAttempts = ArrayDeque(attempts)
        val remainingLoads = ArrayDeque(loads)
        val reattached = mutableListOf<String>()
        val reconnecting = mutableListOf<Boolean>()
        var attemptCalls = 0
        var loadCalls = 0

        val supervisor = RunSupervisor(
            reattach = { id ->
                reattached += id
                emptyFlow()
            },
            load = {
                loadCalls++
                remainingLoads.removeFirst()
            },
            collectAttempt = { _, _ ->
                attemptCalls++
                remainingAttempts.removeFirst()
            },
            setReconnecting = { reconnecting += it },
            backoff = ReconnectBackoff(initialMs = 1_000L, maxMs = 8_000L),
            maxFramelessAttempts = maxFramelessAttempts,
        )
    }

    private fun transient(): Throwable = IOException("connection reset")

    private fun terminal(): Throwable = ApiException(AppError.Http(404, "no such run", fromServer = true))

    private fun serverBug(): Throwable = ApiException(AppError.Http(500, "internal error", fromServer = true))

    private fun attempt(
        error: Throwable? = null,
        runId: String? = null,
        sawAnyFrame: Boolean = false,
        sawTerminal: Boolean = false,
    ) = RunAttempt(error, runId, null, sawAnyFrame, sawTerminal)

    private fun conversation(activeRun: ActiveRun? = null) = ConversationDetail(
        id = "c1",
        title = "t",
        modelRef = ModelRef.Local("llamacpp-a"),
        messages = emptyList(),
        activeRun = activeRun,
        lastRun = null,
        updatedAt = null,
    )

    @Test
    fun `a transient failure with a run id reattaches that run`() = runTest {
        val harness = Harness(
            attempts = listOf(
                attempt(error = transient(), runId = "r1", sawAnyFrame = true),
                attempt(sawAnyFrame = true, sawTerminal = true),
            ),
        )

        val supervision = harness.supervisor.supervise(emptyFlow(), initialRunId = null)

        assertEquals(listOf("r1"), harness.reattached)
        assertEquals(listOf(true), harness.reconnecting)
        assertNull(supervision.error)
        assertTrue(supervision.sawAnyFrame)
    }

    @Test
    fun `an EOF with a live run reconciles and resubscribes the active run`() = runTest {
        val harness = Harness(
            attempts = listOf(
                attempt(runId = "r1", sawAnyFrame = true),
                attempt(sawAnyFrame = true, sawTerminal = true),
            ),
            loads = listOf(Result.success(conversation(ActiveRun("r2", "running", null, null)))),
        )

        val supervision = harness.supervisor.supervise(emptyFlow(), initialRunId = null)

        assertEquals(listOf("r2"), harness.reattached)
        assertEquals(1, harness.loadCalls)
        assertNull(supervision.refetch)
        assertNull(supervision.error)
    }

    @Test
    fun `an EOF with no live run returns the refetched conversation`() = runTest {
        val refetched = conversation()
        val harness = Harness(
            attempts = listOf(attempt(runId = "r1", sawAnyFrame = true)),
            loads = listOf(Result.success(refetched)),
        )

        val supervision = harness.supervisor.supervise(emptyFlow(), initialRunId = null)

        assertEquals(0, harness.reattached.size)
        assertSame(refetched, supervision.refetch?.getOrNull())
        assertNull(supervision.error)
    }

    @Test
    fun `a failure the server will repeat ends the supervision with that error`() = runTest {
        val failure = terminal()
        val harness = Harness(
            attempts = listOf(attempt(error = failure, runId = "r1", sawAnyFrame = true)),
        )

        val supervision = harness.supervisor.supervise(emptyFlow(), initialRunId = null)

        assertSame(failure, supervision.error)
        assertEquals(0, harness.reattached.size)
        assertEquals(0, harness.loadCalls)
    }

    @Test
    fun `a frameless streak ends the supervision instead of retrying forever`() = runTest {
        val bug = serverBug()
        val harness = Harness(
            attempts = List(20) { attempt(error = bug, runId = "r1") },
        )

        val supervision = withTimeout(60_000) {
            harness.supervisor.supervise(emptyFlow(), initialRunId = null)
        }

        assertSame(bug, supervision.error)
        assertEquals("the ceiling allows the first attempt plus seven retries", 8, harness.attemptCalls)
        assertEquals(7, harness.reattached.size)
    }

    @Test
    fun `a frame resets the frameless streak`() = runTest {
        val bug = serverBug()
        val harness = Harness(
            attempts = listOf(
                attempt(error = bug, runId = "r1"),
                attempt(error = bug, runId = "r1"),
                attempt(error = transient(), runId = "r1", sawAnyFrame = true),
                attempt(error = bug, runId = "r1"),
                attempt(error = bug, runId = "r1"),
                attempt(error = bug, runId = "r1"),
                attempt(sawAnyFrame = true, sawTerminal = true),
            ),
            maxFramelessAttempts = 3,
        )

        val supervision = harness.supervisor.supervise(emptyFlow(), initialRunId = null)

        assertSame(bug, supervision.error)
        assertEquals("the streak restarted at the frame-bearing attempt", 6, harness.attemptCalls)
    }

    @Test
    fun `a load that answers resets the frameless streak`() = runTest {
        val bug = serverBug()
        val harness = Harness(
            attempts = listOf(
                attempt(error = bug, runId = "r1"),
                attempt(runId = "r1", sawAnyFrame = true),
                attempt(error = bug, runId = "r1"),
                attempt(error = bug, runId = "r1"),
                attempt(error = bug, runId = "r1"),
                attempt(error = bug, runId = "r1"),
            ),
            loads = listOf(
                Result.failure(bug),
                Result.success(conversation(ActiveRun("r2", "running", null, null))),
            ),
            maxFramelessAttempts = 3,
        )

        val supervision = harness.supervisor.supervise(emptyFlow(), initialRunId = null)

        assertSame(bug, supervision.error)
        assertEquals(
            "the streak restarted when the load answered: one frameless, an EOF, then a fresh count of three",
            5,
            harness.attemptCalls,
        )
        assertEquals(2, harness.loadCalls)
    }

    @Test
    fun `a frameless reconcile streak ends the turn with the load's error`() = runTest {
        val bug = serverBug()
        val harness = Harness(
            attempts = listOf(attempt(runId = "r1", sawAnyFrame = true)),
            loads = List(20) { Result.failure(bug) },
        )

        val supervision = withTimeout(60_000) {
            harness.supervisor.supervise(emptyFlow(), initialRunId = null)
        }

        assertEquals(8, harness.loadCalls)
        assertSame(bug, supervision.refetch?.exceptionOrNull())
        assertNull(supervision.error)
    }

    @Test
    fun `a non-transient load failure is returned on the first try`() = runTest {
        val refused = terminal()
        val harness = Harness(
            attempts = listOf(attempt(runId = "r1", sawAnyFrame = true)),
            loads = listOf(Result.failure(refused)),
        )

        val supervision = harness.supervisor.supervise(emptyFlow(), initialRunId = null)

        assertEquals(1, harness.loadCalls)
        assertSame(refused, supervision.refetch?.exceptionOrNull())
    }

    @Test
    fun `a cancellation from the collector propagates`() = runTest {
        val supervisor = RunSupervisor(
            reattach = { emptyFlow() },
            load = { Result.success(conversation()) },
            collectAttempt = { _, _ -> throw CancellationException("screen went away") },
            setReconnecting = {},
            backoff = ReconnectBackoff(initialMs = 1_000L, maxMs = 8_000L),
        )

        var thrown: Throwable? = null
        try {
            supervisor.supervise(emptyFlow(), initialRunId = null)
        } catch (e: CancellationException) {
            thrown = e
        }
        assertTrue("the supervisor must not swallow a cancellation", thrown is CancellationException)
    }
}
