package com.hpz.llmdockchat.feature.thread

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The settings writer's ordering, rollback and gate, with no HTTP in sight: the
 * three behaviours the screen depends on and the reason this class exists.
 */
class ConversationSettingsWriterTest {

    private class FakeWrites : SettingsWrites {
        val promptWrites = mutableListOf<String?>()
        val serverWrites = mutableListOf<List<String>>()
        var gate: CompletableDeferred<Unit>? = null
        var failPrompt = false

        override suspend fun setPrompt(promptId: String?): Result<Unit> {
            promptWrites += promptId
            gate?.await()
            return if (failPrompt) failure() else Result.success(Unit)
        }

        override suspend fun setMcpServers(serverIds: List<String>): Result<Unit> {
            serverWrites += serverIds
            gate?.await()
            return Result.success(Unit)
        }

        override suspend fun setReasoningLevel(level: String?): Result<Unit> = Result.success(Unit)

        override suspend fun setMainService(wireValue: String): Result<Unit> = Result.success(Unit)

        private fun failure(): Result<Unit> =
            Result.failure(ApiException(AppError.Http(500, "nope", fromServer = true)))
    }

    @Test
    fun `a later write supersedes an earlier one and keeps the newest value`() = runTest {
        val writes = FakeWrites()
        var latest: SettingsSnapshot? = null
        val writer = ConversationSettingsWriter(writes, CoroutineScope(UnconfinedTestDispatcher(testScheduler))) { latest = it }
        writer.seed("p0", emptyList(), null)

        writer.selectPrompt("p1")
        writer.selectPrompt("p2")

        assertEquals("p2", latest?.promptId)
        assertEquals("p2", writer.snapshotForTest().promptId)
    }

    @Test
    fun `a failed write rolls back to the confirmed value`() = runTest {
        val writes = FakeWrites().apply { failPrompt = true }
        var latest: SettingsSnapshot? = null
        val writer = ConversationSettingsWriter(writes, CoroutineScope(UnconfinedTestDispatcher(testScheduler))) { latest = it }
        writer.seed("confirmed", emptyList(), null)

        writer.selectPrompt("attempted")

        assertEquals("confirmed", latest?.promptId)
        assertEquals("nope", latest?.error)
    }

    @Test
    fun `the gate is counted before the write starts, so a send on the same turn is blocked`() = runTest {
        val writes = FakeWrites().apply { gate = CompletableDeferred() }
        val writer = ConversationSettingsWriter(writes, CoroutineScope(StandardTestDispatcher(testScheduler))) {}
        writer.seed(null, emptyList(), null)
        assertFalse(writer.pending)

        writer.toggleTool("sympy-math")

        assertTrue("the count must be visible before the coroutine runs", writer.pending)
        assertTrue(writes.serverWrites.isEmpty())

        writes.gate?.complete(Unit)
        testScheduler.advanceUntilIdle()
        assertFalse(writer.pending)
        assertNull(null)
    }
}
