package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.buildPiTranscript
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

@OptIn(ExperimentalCoroutinesApi::class)
class PiCacheResumeTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun `cached paint precedes network and actual first request resumes accepted cursor`() = runTest {
        val fixture = PiRuntimeFixture(temporary.newFolder(), backgroundScope, StandardTestDispatcher(testScheduler), { currentTime })
        val seed = resumeSnapshot()
        fixture.store.enqueue(fixture.store.generation(seed.identity), seed).await()
        val transport = DrivenPiTransport()
        val runtime = fixture.runtime(transport, seed.identity.key)
        transport.opening = {
            assertEquals(PiSessionPhase.CACHED_CHECKING, (runtime.state.value as PiSessionUiState.Loaded).phase)
            assertEquals(seed.checkpoint.items, (runtime.state.value as PiSessionUiState.Loaded).transcript.items)
        }
        runtime.start(backgroundScope)
        runCurrent()
        assertEquals("4", transport.requests.single().query["after"])
        assertEquals(fixture.server, transport.requests.single().expectedServer)
        assertNull(runtime.commandServer())
        transport.send(piBatch(9, "fix"))
        runCurrent()
        assertEquals(PiSessionPhase.CATCHING_UP, (runtime.state.value as PiSessionUiState.Loaded).phase)
        assertEquals(4L, fixture.store.read(seed.identity)?.lastSeq)
        assertNull(runtime.commandServer())
        transport.send(resumeSummary())
        runCurrent()
        val loaded = runtime.state.value as PiSessionUiState.Loaded
        val full = buildPiTranscript(resumePrefix + piEvent(9, "assistant_delta", """{"text":"fix"}"""))
        assertEquals(full, loaded.transcript)
        assertEquals(PiSessionPhase.CONNECTED, loaded.phase)
        assertEquals(fixture.server, runtime.commandServer())
        val committed = fixture.store.read(seed.identity)!!
        assertEquals(9L, committed.lastSeq)
        assertEquals(full, com.hpz.llmdockchat.feature.pi.transcript.TranscriptBuilder(committed.checkpoint).transcript())
        runtime.stop()
    }

    @Test
    fun `miss requests zero and failure keeps cached content read only until post replay summary`() = runTest {
        val fixture = PiRuntimeFixture(temporary.newFolder(), backgroundScope, StandardTestDispatcher(testScheduler), { currentTime })
        val transport = DrivenPiTransport()
        val runtime = fixture.runtime(transport)
        runtime.start(backgroundScope)
        runCurrent()
        assertEquals("0", transport.requests.single().query["after"])
        transport.send(piBatch(1, "visible"))
        transport.send(piSummary())
        runCurrent()
        val before = runtime.state.value as PiSessionUiState.Loaded
        assertEquals(PiSessionPhase.CONNECTED, before.phase)
        transport.fail(java.io.IOException("offline"))
        runCurrent()
        val offline = runtime.state.value as PiSessionUiState.Loaded
        assertEquals(before.transcript, offline.transcript)
        assertEquals(PiSessionPhase.RECONNECTING, offline.phase)
        assertFalse(offline.commandsAvailable)
        advanceTimeBy(3_000)
        runCurrent()
        assertEquals("1", transport.requests[1].query["after"])
        transport.send(piBatch(2, " tail"))
        runCurrent()
        assertEquals(PiSessionPhase.CATCHING_UP, (runtime.state.value as PiSessionUiState.Loaded).phase)
        assertNull(runtime.commandServer())
        transport.send(piSummary())
        runCurrent()
        assertEquals(PiSessionPhase.CONNECTED, (runtime.state.value as PiSessionUiState.Loaded).phase)
        runtime.stop()
    }

    @Test
    fun `firstSeen mismatch discards tentative suffix restarts from zero once and never saves wrong history`() = runTest {
        val fixture = PiRuntimeFixture(temporary.newFolder(), backgroundScope, StandardTestDispatcher(testScheduler), { currentTime })
        val seed = resumeSnapshot()
        fixture.store.enqueue(fixture.store.generation(seed.identity), seed).await()
        val transport = DrivenPiTransport()
        val runtime = fixture.runtime(transport, seed.identity.key)
        runtime.start(backgroundScope)
        runCurrent()
        transport.send(piBatch(9, "WRONG"))
        runCurrent()
        assertEquals(seed, fixture.store.read(seed.identity))
        transport.send(resumeSummary(200))
        runCurrent()
        assertEquals(listOf("4", "0"), transport.requests.map { it.query["after"] })
        assertNull(fixture.store.read(seed.identity))
        transport.send(piBatch(1, "new"))
        transport.send(resumeSummary(200))
        runCurrent()
        val committed = fixture.store.read(seed.identity)!!
        assertEquals(200L, committed.firstSeen)
        assertEquals(1L, committed.lastSeq)
        assertEquals("new", (committed.checkpoint.items.single() as PiItem.Assistant).text)
        transport.send(resumeSummary(300))
        runCurrent()
        val failure = runtime.state.value as PiSessionUiState.Loaded
        assertEquals(PiSessionPhase.FAILED, failure.phase)
        assertTrue(failure.transcript.items.isEmpty())
        assertEquals(2, transport.requests.size)
        assertNull(fixture.store.read(seed.identity))
        runtime.stop()
    }
}
