package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotIdentity
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

@OptIn(ExperimentalCoroutinesApi::class)
class PiCheckpointTimingTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun `continuous dirty events use a fixed trailing deadline rather than debounce`() = runTest {
        val saved = mutableListOf<Pair<Long, Long>>()
        val writer = PiCheckpointWriter(backgroundScope, { currentTime }) { saved += currentTime to it.lastSeq }
        writer.changed(snapshot(seq = 1))
        for (seq in 2L..10L) {
            advanceTimeBy(1_000)
            runCurrent()
            writer.changed(snapshot(seq = seq))
        }
        advanceTimeBy(1_000)
        runCurrent()
        assertEquals(listOf(0L to 1L, 5_000L to 5L, 10_000L to 10L), saved)
        writer.close()
    }

    @Test
    fun `runtime commits consistent cursor and checkpoint promptly then at five second intervals`() = runTest {
        val fixture = PiRuntimeFixture(temporary.newFolder(), backgroundScope, StandardTestDispatcher(testScheduler), { currentTime })
        val transport = DrivenPiTransport()
        val runtime = fixture.runtime(transport)
        val identity = PiSnapshotIdentity(fixture.server.value, PiSessionKey("s1", "i1"))
        runtime.start(backgroundScope)
        runCurrent()
        transport.send(piBatch(1, "A"))
        runCurrent()
        assertEquals(null, fixture.store.read(identity))
        transport.send(piSummary())
        runCurrent()
        assertEquals(1L, fixture.store.read(identity)?.lastSeq)
        advanceTimeBy(1_000)
        transport.send(piBatch(2, "B"))
        runCurrent()
        advanceTimeBy(3_999)
        runCurrent()
        assertEquals(1L, fixture.store.read(identity)?.lastSeq)
        advanceTimeBy(1)
        runCurrent()
        val saved = fixture.store.read(identity)!!
        assertEquals(2L, saved.lastSeq)
        assertEquals("AB", (saved.checkpoint.items.single() as com.hpz.llmdockchat.feature.pi.transcript.PiItem.Assistant).text)
        runtime.stop()
    }

    @Test
    fun `navigation cancellation and background flush persist latest validated state outside VM scope`() = runTest {
        val fixture = PiRuntimeFixture(temporary.newFolder(), backgroundScope, StandardTestDispatcher(testScheduler), { currentTime })
        val transport = DrivenPiTransport()
        val runtime = fixture.runtime(transport)
        val identity = PiSnapshotIdentity(fixture.server.value, PiSessionKey("s1", "i1"))
        runtime.start(backgroundScope)
        runCurrent()
        transport.send(piBatch(1, "A")); transport.send(piSummary())
        runCurrent()
        advanceTimeBy(1_000)
        transport.send(piBatch(2, "B"))
        runCurrent()
        runtime.flush()
        runCurrent()
        assertEquals(2L, fixture.store.read(identity)?.lastSeq)
        advanceTimeBy(1_000)
        transport.send(piBatch(3, "C"))
        runCurrent()
        runtime.stop()
        runCurrent()
        assertEquals(3L, fixture.store.read(identity)?.lastSeq)
        val reopenedTransport = DrivenPiTransport()
        val reopened = fixture.runtime(reopenedTransport)
        reopened.start(backgroundScope)
        runCurrent()
        assertEquals("3", reopenedTransport.requests.single().query["after"])
        reopened.stop()
    }
}
