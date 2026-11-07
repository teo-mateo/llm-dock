package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.feature.pi.transcript.TranscriptBuilder
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
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
class PiLeaseRemovalTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun `same key replacement after initial current check fences stale removal`() = runTest {
        assertRemovalIsScoped(switchServer = false)
    }

    @Test
    fun `server switch after initial current check fences stale removal`() = runTest {
        assertRemovalIsScoped(switchServer = true)
    }

    private suspend fun TestScope.assertRemovalIsScoped(switchServer: Boolean) {
        val directory = temporary.newFolder()
        val files = ControlledPiSnapshotFiles(directory)
        val fixture = PiRuntimeFixture(directory, backgroundScope, StandardTestDispatcher(testScheduler), { currentTime }, files)
        val original = resumeSnapshot()
        val old = fixture.cache.open(original.identity.key) {}!!
        assertTrue(fixture.cache.current(old))
        if (switchServer) fixture.switch(BaseUrl.restore("https://replacement.example")!!)
        val snapshot = original.copy(identity = original.identity.copy(server = fixture.server.value))
        var display: PiSessionUiState = PiSessionUiState.Loading
        val replacement = fixture.cache.open(snapshot.identity.key) { removed ->
            display = if (removed) PiSessionUiState.Unknown else PiSessionUiState.Loading
        }!!
        val loaded = PiSessionUiState.Loaded(
            snapshot.summary, TranscriptBuilder(snapshot.checkpoint).transcript(), PiSessionPhase.CONNECTED,
        )
        assertTrue(fixture.cache.publish(replacement) { display = loaded })
        val gate = SnapshotWriteGate().also { files.gate = it }
        val write = fixture.cache.enqueue(replacement, replacement.generation, snapshot)
        try {
            gate.prepared.await()
            assertFalse(fixture.cache.remove(old))
            assertSame(loaded, display)
            assertTrue(fixture.cache.current(replacement))
            gate.release.complete(Unit)
            assertEquals(PiSnapshotWriteResult.Stored, write.await())
            assertEquals(snapshot, fixture.store.read(snapshot.identity))
            assertTrue(fixture.cache.remove(replacement))
            runCurrent()
            assertSame(PiSessionUiState.Unknown, display)
            assertFalse(fixture.cache.current(replacement))
            assertNull(fixture.store.read(snapshot.identity))
        } finally {
            gate.release.complete(Unit)
            fixture.cache.release(old)
            fixture.cache.release(replacement)
        }
    }
}
