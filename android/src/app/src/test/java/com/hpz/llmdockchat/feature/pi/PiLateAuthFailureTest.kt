package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.SseTransport
import com.hpz.llmdockchat.core.net.StreamRequest
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotIdentity
import kotlin.coroutines.Continuation
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

@OptIn(ExperimentalCoroutinesApi::class)
class PiLateAuthFailureTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun `late old server auth failure leaves replacement display lease and pending writes valid`() = runTest {
        assertReplacementSurvives(switchServer = true)
    }

    @Test
    fun `late same key auth failure leaves replacement display lease and pending writes valid`() = runTest {
        assertReplacementSurvives(switchServer = false)
    }

    private suspend fun TestScope.assertReplacementSurvives(switchServer: Boolean) {
        val directory = temporary.newFolder()
        val files = ControlledPiSnapshotFiles(directory)
        val fixture = PiRuntimeFixture(directory, backgroundScope, StandardTestDispatcher(testScheduler), { currentTime }, files)
        val oldTransport = LateAuthTransport()
        val old = fixture.runtime(oldTransport)
        val replacementTransport = DrivenPiTransport()
        val replacement = fixture.runtime(replacementTransport)
        val gate = SnapshotWriteGate().also { files.gate = it }
        old.start(backgroundScope)
        val lateFailure = oldTransport.waiting.await()
        var delivered = false
        try {
            if (switchServer) fixture.switch(BaseUrl.restore("https://replacement.example")!!)
            replacement.start(backgroundScope)
            runCurrent()
            replacementTransport.send(piBatch(1, "B")); replacementTransport.send(piSummary())
            gate.prepared.await()
            replacementTransport.send(piBatch(2, "C"))
            runCurrent()
            advanceTimeBy(5_000)
            runCurrent()
            val identity = PiSnapshotIdentity(fixture.server.value, PiSessionKey("s1", "i1"))
            val generation = fixture.store.generation(identity)
            val display = replacement.state.value as PiSessionUiState.Loaded
            assertEquals(PiSessionPhase.CONNECTED, display.phase)
            assertEquals("BC", (display.transcript.items.single() as PiItem.Assistant).text)
            assertEquals(fixture.server, replacement.commandServer())
            assertEquals(1, files.activePreparations)
            delivered = true
            lateFailure.resumeWithException(ApiException(AppError.Unauthenticated))
            runCurrent()
            assertTrue(oldTransport.finished.isCompleted)
            assertSame(display, replacement.state.value)
            assertEquals(fixture.server, replacement.commandServer())
            assertTrue(fixture.store.isCurrent(generation))
            gate.release.complete(Unit)
            runCurrent()
            val committed = fixture.store.read(identity)!!
            assertEquals(2L, committed.lastSeq)
            assertEquals("BC", (committed.checkpoint.items.single() as PiItem.Assistant).text)
            assertSame(display, replacement.state.value)
        } finally {
            if (!delivered) lateFailure.resumeWithException(CancellationException("Test finished"))
            gate.release.complete(Unit)
            old.stop()
            replacement.stop()
        }
    }

    @Test
    fun `current context auth failure still clears displays and invalidates unfinished writes without deleting commits`() = runTest {
        val directory = temporary.newFolder()
        val files = ControlledPiSnapshotFiles(directory)
        val fixture = PiRuntimeFixture(directory, backgroundScope, StandardTestDispatcher(testScheduler), { currentTime }, files)
        val seed = resumeSnapshot()
        fixture.store.enqueue(fixture.store.generation(seed.identity), seed).await()
        val primaryTransport = DrivenPiTransport()
        val primary = fixture.runtime(primaryTransport, seed.identity.key)
        val otherTransport = DrivenPiTransport()
        val otherKey = PiSessionKey("other", "i1")
        val other = fixture.runtime(otherTransport, otherKey)
        val gate = SnapshotWriteGate().also { files.gate = it }
        try {
            primary.start(backgroundScope)
            runCurrent()
            primaryTransport.send(piBatch(9, "suffix")); primaryTransport.send(resumeSummary())
            gate.prepared.await()
            other.start(backgroundScope)
            runCurrent()
            otherTransport.send(piBatch(1, "other")); otherTransport.send(piSummary(session = "other"))
            runCurrent()
            val otherIdentity = PiSnapshotIdentity(fixture.server.value, otherKey)
            val primaryGeneration = fixture.store.generation(seed.identity)
            val otherGeneration = fixture.store.generation(otherIdentity)
            assertEquals(fixture.server, primary.commandServer())
            assertEquals(fixture.server, other.commandServer())
            primaryTransport.fail(ApiException(AppError.Unauthenticated))
            runCurrent()
            assertSame(PiSessionUiState.Loading, primary.state.value)
            assertSame(PiSessionUiState.Loading, other.state.value)
            assertNull(primary.commandServer())
            assertNull(other.commandServer())
            assertFalse(fixture.store.isCurrent(primaryGeneration))
            assertFalse(fixture.store.isCurrent(otherGeneration))
            gate.release.complete(Unit)
            runCurrent()
            assertEquals(seed, fixture.store.read(seed.identity))
            assertNull(fixture.store.read(otherIdentity))
        } finally {
            gate.release.complete(Unit)
            primary.stop()
            other.stop()
        }
    }
}

private class LateAuthTransport : SseTransport {
    val waiting = CompletableDeferred<Continuation<Unit>>()
    val finished = CompletableDeferred<Unit>()

    override fun open(request: StreamRequest) = flow<String> {
        try {
            suspendCoroutine<Unit> { waiting.complete(it) }
        } finally {
            finished.complete(Unit)
        }
    }
}
