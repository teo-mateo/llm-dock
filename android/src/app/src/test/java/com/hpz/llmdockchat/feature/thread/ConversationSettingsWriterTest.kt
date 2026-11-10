package com.hpz.llmdockchat.feature.thread

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The writer's ordering, rollback, gate and error delivery, with a fake
 * [SettingsWrites] and no HTTP: the four behaviours the screen depends on.
 */
class ConversationSettingsWriterTest {

    private class FakeWrites : SettingsWrites {
        val promptWrites = mutableListOf<String?>()
        val serverWrites = mutableListOf<List<String>>()
        val levelWrites = mutableListOf<String?>()
        var gate: CompletableDeferred<Unit>? = null
        val gates = ArrayDeque<CompletableDeferred<Unit>>()
        var failPrompt = false
        var failTools = false

        override suspend fun setPrompt(promptId: String?): Result<Unit> {
            promptWrites += promptId
            (gates.removeFirstOrNull() ?: gate)?.await()
            return if (failPrompt) failure() else Result.success(Unit)
        }

        override suspend fun setMcpServers(serverIds: List<String>): Result<Unit> {
            serverWrites += serverIds
            (gates.removeFirstOrNull() ?: gate)?.await()
            return if (failTools) failure() else Result.success(Unit)
        }

        override suspend fun setReasoningLevel(level: String?): Result<Unit> {
            levelWrites += level
            gate?.await()
            return Result.success(Unit)
        }

        private fun failure(): Result<Unit> =
            Result.failure(ApiException(AppError.Http(500, "nope", fromServer = true)))
    }

    private class Recorder {
        var latest: SettingsSnapshot? = null
        val errors = mutableListOf<String>()
        var confirmed = 0
    }

    private fun writer(
        writes: FakeWrites,
        scope: CoroutineScope,
        recorder: Recorder,
    ) = ConversationSettingsWriter(
        writes = writes,
        scope = scope,
        onReasoningConfirmed = { recorder.confirmed++ },
        onError = { recorder.errors += it },
        onSnapshot = { recorder.latest = it },
    )

    @Test
    fun `a later write supersedes an earlier one and only the newest reaches the server`() = runTest {
        val writes = FakeWrites()
        val recorder = Recorder()
        val writer = writer(writes, CoroutineScope(StandardTestDispatcher(testScheduler)), recorder)
        writer.seed("p0", emptyList(), null)
        val gate = CompletableDeferred<Unit>().also { writes.gate = it }

        writer.selectPrompt("p1")
        writer.selectPrompt("p2")
        testScheduler.advanceUntilIdle()
        gate.complete(Unit)
        testScheduler.advanceUntilIdle()

        assertEquals("only the newest write is sent", listOf("p2"), writes.promptWrites)
        assertEquals("p2", recorder.latest?.promptId)
    }

    @Test
    fun `a failed write rolls back to the confirmed value and reports once`() = runTest {
        val writes = FakeWrites().apply { failPrompt = true }
        val recorder = Recorder()
        val writer = writer(writes, CoroutineScope(StandardTestDispatcher(testScheduler)), recorder)
        writer.seed("confirmed", emptyList(), null)

        writer.selectPrompt("attempted")
        testScheduler.advanceUntilIdle()

        assertEquals("confirmed", recorder.latest?.promptId)
        assertEquals(listOf("nope"), recorder.errors)
    }

    @Test
    fun `a completed write after a failure does not replay the error`() = runTest {
        val writes = FakeWrites().apply { failPrompt = true }
        val recorder = Recorder()
        val writer = writer(writes, CoroutineScope(StandardTestDispatcher(testScheduler)), recorder)
        writer.seed(null, emptyList(), null)

        writer.selectPrompt("first")
        testScheduler.advanceUntilIdle()
        writes.failPrompt = false
        writer.toggleTool("sympy-math")
        testScheduler.advanceUntilIdle()

        assertEquals("the error is an event, delivered once", listOf("nope"), recorder.errors)
    }

    @Test
    fun `a failed tool write rolls back to the list the server confirmed`() = runTest {
        val writes = FakeWrites()
        val recorder = Recorder()
        val writer = writer(writes, CoroutineScope(StandardTestDispatcher(testScheduler)), recorder)
        writer.seed(null, listOf("a"), null)

        writer.toggleTool("b")
        testScheduler.advanceUntilIdle()
        writes.failTools = true
        writer.toggleTool("c")
        testScheduler.advanceUntilIdle()

        assertEquals("the rollback is the confirmed list, not the previous guess", listOf("a", "b"), recorder.latest?.mcpServers)
    }

    @Test
    fun `a superseded level write neither confirms nor closes the picker`() = runTest {
        val writes = FakeWrites()
        val recorder = Recorder()
        val writer = writer(writes, CoroutineScope(StandardTestDispatcher(testScheduler)), recorder)
        writer.seed(null, emptyList(), null)
        val gate = CompletableDeferred<Unit>().also { writes.gate = it }

        writer.selectReasoningLevel("low")
        writer.selectReasoningLevel("high")
        testScheduler.advanceUntilIdle()
        gate.complete(Unit)
        testScheduler.advanceUntilIdle()

        assertEquals("both are sent, in order", listOf("low", "high"), writes.levelWrites)
        assertEquals("one confirmation, for the newest write", 1, recorder.confirmed)
        assertEquals("high", recorder.latest?.reasoningLevel)
        assertFalse(recorder.latest?.reasoningPending ?: true)
    }

    @Test
    fun `the gate is counted before the write starts, so a send on the same turn is blocked`() = runTest {
        val writes = FakeWrites().apply { gate = CompletableDeferred() }
        val recorder = Recorder()
        val writer = writer(writes, CoroutineScope(StandardTestDispatcher(testScheduler)), recorder)
        writer.seed(null, emptyList(), null)
        assertFalse(writer.pending)

        writer.toggleTool("sympy-math")

        assertTrue("the count must be visible before the coroutine runs", writer.pending)
        assertTrue(writes.serverWrites.isEmpty())

        writes.gate?.complete(Unit)
        testScheduler.advanceUntilIdle()
        assertFalse(writer.pending)
    }

    @Test
    fun `a seed after the first of two queued writes finished keeps the chosen value`() = runTest {
        val writes = FakeWrites()
        val recorder = Recorder()
        val writer = writer(writes, CoroutineScope(StandardTestDispatcher(testScheduler)), recorder)
        writer.seed(null, listOf("a"), null)
        val first = CompletableDeferred<Unit>()
        val second = CompletableDeferred<Unit>()
        writes.gates.addAll(listOf(first, second))

        writer.toggleTool("b")
        writer.toggleTool("c")
        testScheduler.advanceUntilIdle()
        first.complete(Unit)
        testScheduler.advanceUntilIdle()

        writer.seed(null, listOf("a"), null)

        assertEquals(
            "the second write is still outstanding, so the chosen list stays",
            listOf("a", "b", "c"),
            recorder.latest?.mcpServers,
        )
        second.complete(Unit)
        testScheduler.advanceUntilIdle()
    }

    @Test
    fun `a seed during a write keeps the value the user chose`() = runTest {
        val writes = FakeWrites()
        val recorder = Recorder()
        val writer = writer(writes, CoroutineScope(StandardTestDispatcher(testScheduler)), recorder)
        writer.seed("p0", emptyList(), null)
        val gate = CompletableDeferred<Unit>().also { writes.gate = it }

        writer.selectPrompt("chosen")
        testScheduler.advanceUntilIdle()

        writer.seed("stale", emptyList(), null)

        assertEquals("the server copy is older than the write in flight", "chosen", recorder.latest?.promptId)

        gate.complete(Unit)
        testScheduler.advanceUntilIdle()
        assertEquals("chosen", recorder.latest?.promptId)
    }
}
