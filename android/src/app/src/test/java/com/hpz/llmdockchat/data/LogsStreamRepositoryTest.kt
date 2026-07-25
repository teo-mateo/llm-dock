package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.LogStreamEvent
import com.hpz.llmdockchat.testing.FakeSseTransport
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * [LogsStreamRepository.stream] — the transport wiring only (parsing itself
 * is [com.hpz.llmdockchat.core.net.LogStreamEventTest]'s job). Deliberately no
 * "keeps retrying" test here, unlike [GpuStreamRepositoryTest] and
 * [ServicesStreamRepositoryTest]'s: this repository does not loop, by design
 * (see its class doc) — a `stream_end` is a normal outcome, not something to
 * reconnect into.
 */
class LogsStreamRepositoryTest {

    @Test
    fun `frames arrive in order, unparsed types passed straight through`() = runTest {
        val transport = FakeSseTransport()
        transport.payloads = listOf(
            """{"type":"snapshot_start"}""",
            """{"type":"log","line":"first line"}""",
            """{"type":"snapshot_end"}""",
            """{"type":"log","line":"second line"}""",
            """{"type":"stream_end"}""",
        )
        val repository = LogsStreamRepository(transport)

        val events = withTimeout(5_000) { repository.stream("llamacpp-a").toList() }

        assertEquals(
            listOf(
                LogStreamEvent.SnapshotStart,
                LogStreamEvent.Log("first line"),
                LogStreamEvent.SnapshotEnd,
                LogStreamEvent.Log("second line"),
                LogStreamEvent.StreamEnd,
            ),
            events,
        )
        assertEquals("200", transport.requests.single().query["tail"])
    }

    /**
     * The mechanism, not a flag — same pattern as
     * [GpuStreamRepositoryTest]'s "cancelling the collector actually tears
     * down the open connection": a collector going away (leaving the logs
     * screen, F12-R1's last criterion) must actually cancel the underlying
     * transport call, not just stop reading from it.
     */
    @Test
    fun `cancelling the collector tears down the open connection`() = runTest {
        val transport = FakeSseTransport()
        transport.stayOpen = true
        val repository = LogsStreamRepository(transport)

        val job: Job = launch { repository.stream("llamacpp-a").collect { } }
        withTimeout(5_000) { transport.parked.await() }

        job.cancel()
        withTimeout(5_000) { transport.cancelled.await() }
    }
}
