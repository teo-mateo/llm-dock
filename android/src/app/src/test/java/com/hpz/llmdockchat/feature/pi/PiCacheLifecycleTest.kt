package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.core.net.BaseUrl
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

@OptIn(ExperimentalCoroutinesApi::class)
class PiCacheLifecycleTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun `sign out invalidates prepared write immediately and reauthentication cannot revive old work`() = runTest {
        val directory = temporary.newFolder()
        val files = ControlledPiSnapshotFiles(directory)
        val fixture = PiRuntimeFixture(directory, backgroundScope, StandardTestDispatcher(testScheduler), { currentTime }, files)
        val seed = resumeSnapshot()
        fixture.store.enqueue(fixture.store.generation(seed.identity), seed).await()
        val gate = SnapshotWriteGate().also { files.gate = it }
        val transport = DrivenPiTransport()
        val runtime = fixture.runtime(transport, seed.identity.key)
        runtime.start(backgroundScope)
        runCurrent()
        transport.send(piBatch(9, "tentative")); transport.send(resumeSummary())
        gate.prepared.await()
        fixture.auth.signedOut()
        assertSame(PiSessionUiState.Loading, runtime.state.value)
        assertNull(runtime.commandServer())
        val signedOut = fixture.runtime(DrivenPiTransport(), seed.identity.key)
        signedOut.start(backgroundScope)
        runCurrent()
        assertSame(PiSessionUiState.Loading, signedOut.state.value)
        fixture.auth.authenticated()
        transport.send(piBatch(10, "must not revive"))
        gate.release.complete(Unit)
        runCurrent()
        assertSame(PiSessionUiState.Loading, runtime.state.value)
        assertEquals(seed, fixture.store.read(seed.identity))
        assertEquals(1, transport.requests.size)
        val reopenedTransport = DrivenPiTransport()
        val reopened = fixture.runtime(reopenedTransport, seed.identity.key)
        reopened.start(backgroundScope)
        runCurrent()
        assertEquals("4", reopenedTransport.requests.single().query["after"])
        assertEquals(seed.checkpoint.items, (reopened.state.value as PiSessionUiState.Loaded).transcript.items)
        reopened.stop()
    }

    @Test
    fun `server switch between validation and reconnect cancels old work even after switching back`() = runTest {
        val fixture = PiRuntimeFixture(temporary.newFolder(), backgroundScope, StandardTestDispatcher(testScheduler), { currentTime })
        val seed = resumeSnapshot()
        fixture.store.enqueue(fixture.store.generation(seed.identity), seed).await()
        val transport = DrivenPiTransport()
        val runtime = fixture.runtime(transport, seed.identity.key)
        runtime.start(backgroundScope)
        runCurrent()
        transport.send(resumeSummary())
        runCurrent()
        transport.fail(java.io.IOException("offline"))
        runCurrent()
        advanceTimeBy(2_999)
        val originalServer = fixture.server
        fixture.switch(BaseUrl.restore("https://other.example")!!)
        assertSame(PiSessionUiState.Loading, runtime.state.value)
        val otherTransport = DrivenPiTransport()
        val other = fixture.runtime(otherTransport, seed.identity.key)
        other.start(backgroundScope)
        runCurrent()
        assertEquals("0", otherTransport.requests.single().query["after"])
        assertEquals(fixture.server, otherTransport.requests.single().expectedServer)
        fixture.switch(originalServer)
        transport.send(piBatch(9, "late"))
        advanceTimeBy(60_000)
        runCurrent()
        assertEquals(1, transport.requests.size)
        assertSame(PiSessionUiState.Loading, runtime.state.value)
        assertEquals(4L, fixture.store.read(seed.identity)?.lastSeq)
        other.stop()
    }

    @Test
    fun `404 and explicit removal clear cache without a prepared write resurrecting it`() = runTest {
        for (explicit in listOf(false, true)) {
            val directory = temporary.newFolder()
            val files = ControlledPiSnapshotFiles(directory)
            val fixture = PiRuntimeFixture(directory, backgroundScope, StandardTestDispatcher(testScheduler), { currentTime }, files)
            val seed = resumeSnapshot()
            fixture.store.enqueue(fixture.store.generation(seed.identity), seed).await()
            val gate = SnapshotWriteGate().also { files.gate = it }
            val transport = DrivenPiTransport()
            val runtime = fixture.runtime(transport, seed.identity.key)
            runtime.start(backgroundScope)
            runCurrent()
            transport.send(piBatch(9, "suffix")); transport.send(resumeSummary())
            gate.prepared.await()
            if (explicit) transport.send("""{"type":"session_removed","session_id":"session","instance_id":"instance"}""")
            else transport.fail(ApiException(AppError.Http(404, "unknown_session", true)))
            runCurrent()
            assertSame(PiSessionUiState.Unknown, runtime.state.value)
            gate.release.complete(Unit)
            runCurrent()
            assertNull(fixture.store.read(seed.identity))
            assertTrue(directory.listFiles()!!.isEmpty())
            advanceTimeBy(60_000)
            runCurrent()
            assertEquals(1, transport.requests.size)
        }
    }

    @Test
    fun `replacing an active stream for the same key stops the old reducer`() = runTest {
        val fixture = PiRuntimeFixture(temporary.newFolder(), backgroundScope, StandardTestDispatcher(testScheduler), { currentTime })
        val firstTransport = DrivenPiTransport()
        val first = fixture.runtime(firstTransport)
        first.start(backgroundScope)
        runCurrent()
        firstTransport.send(piBatch(1, "A")); firstTransport.send(piSummary())
        runCurrent()
        val secondTransport = DrivenPiTransport()
        val second = fixture.runtime(secondTransport)
        second.start(backgroundScope)
        runCurrent()
        firstTransport.send(piBatch(2, "late"))
        runCurrent()
        assertSame(PiSessionUiState.Loading, first.state.value)
        assertEquals("1", secondTransport.requests.single().query["after"])
        second.stop()
    }
}
