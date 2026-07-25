package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.ServiceStreamEvent
import com.hpz.llmdockchat.data.dto.ServiceDto
import com.hpz.llmdockchat.data.model.ServiceSummary
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.ScriptedSseTransport
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * [mergeServiceEvent] (pure — the reduce step) and [ServicesStreamRepository.stream]
 * (the transport wiring) separately, same split as [core.net.RunEventParserTest]
 * versus [ChatRepositoryTest].
 */
class ServicesStreamRepositoryTest {

    private val running = ServiceSummary("llamacpp-a", "running", "chat", port = 3301, favorite = false)
    private val stopped = ServiceSummary("vllm-b", "exited", "chat", port = 3302, favorite = true)

    @Test
    fun `a snapshot replaces the list wholesale`() {
        val snapshot = ServiceStreamEvent.Snapshot(
            listOf(
                ServiceDto("llamacpp-a", "running", "chat", 3301, false),
                ServiceDto("vllm-b", "exited", "chat", 3302, true),
            ),
        )
        val result = mergeServiceEvent(emptyList(), snapshot)
        assertEquals(listOf(running, stopped), result)
    }

    @Test
    fun `a delta updates only the named service, leaving the rest untouched`() {
        val delta = ServiceStreamEvent.Delta(serviceName = "llamacpp-a", status = "exited", favorite = null)
        val result = mergeServiceEvent(listOf(running, stopped), delta)
        assertEquals(listOf(running.copy(status = "exited"), stopped), result)
    }

    @Test
    fun `a delta's favorite overrides the stored flag when present`() {
        val delta = ServiceStreamEvent.Delta(serviceName = "llamacpp-a", status = null, favorite = true)
        val result = mergeServiceEvent(listOf(running, stopped), delta)
        assertEquals(running.copy(favorite = true), result[0])
    }

    @Test
    fun `a delta for an unknown service name changes nothing`() {
        val delta = ServiceStreamEvent.Delta(serviceName = "does-not-exist", status = "running", favorite = null)
        assertEquals(listOf(running, stopped), mergeServiceEvent(listOf(running, stopped), delta))
    }

    @Test
    fun `an error or unknown frame leaves the current list exactly as it was`() {
        val current = listOf(running, stopped)
        assertEquals(current, mergeServiceEvent(current, ServiceStreamEvent.Error("boom")))
        assertEquals(current, mergeServiceEvent(current, ServiceStreamEvent.Unknown("garbage")))
    }

    // -- the transport wiring --------------------------------------------------

    @Test
    fun `stream emits the mapped list for a snapshot then a delta, in order`() = runTest {
        val transport = FakeSseTransport()
        transport.payloads = listOf(
            """{"type":"snapshot","data":{"services":[
                {"name":"llamacpp-a","status":"running","kind":"chat","host_port":3301,"favorite":false}
            ],"total":1,"running":1,"stopped":0}}""",
            """{"type":"delta","service_name":"llamacpp-a","status":"exited"}""",
        )
        val repository = ServicesStreamRepository(transport)

        // `take(2)` cancels the upstream right after the second emission,
        // before the fake transport's flow would complete and the reconnect
        // loop would open a second, empty connection.
        val emissions = withTimeout(5_000) { repository.stream().take(2).toList() }

        assertEquals("running", emissions[0][0].status)
        assertEquals("exited", emissions[1][0].status)
    }

    // -- streamWithStatus (F10-R1's fifth criterion) ----------------------------

    @Test
    fun `streamWithStatus is not stale while the connection is up`() = runTest {
        val transport = FakeSseTransport()
        transport.payloads = listOf(
            """{"type":"snapshot","data":{"services":[
                {"name":"llamacpp-a","status":"running","kind":"chat","host_port":3301,"favorite":false}
            ],"total":1,"running":1,"stopped":0}}""",
        )
        val repository = ServicesStreamRepository(transport)

        val emission = withTimeout(5_000) { repository.streamWithStatus().take(1).toList() }.single()

        assertEquals(false, emission.stale)
        assertEquals(listOf(running), emission.services)
    }

    /**
     * A dropped connection must not freeze the last-known list — it is
     * re-emitted immediately with `stale = true` carrying the last snapshot
     * forward, rather than the collector hearing nothing until the next
     * successful reconnect (F10-R1's fifth criterion: "falls back to a
     * snapshot fetch and shows a stale indicator rather than freezing").
     * Against a `stream()`-only design (before `streamWithStatus` existed)
     * this drop would simply never be observed at all — no emission, no
     * indicator, exactly the "freezing" the requirement rules out. A single
     * [ScriptedSseTransport.Leg] carries both halves of one real connection:
     * a snapshot arrives, then the same connection drops mid-stream.
     */
    @Test
    fun `a dropped connection is re-emitted immediately as stale, with the last known list intact`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(
            ScriptedSseTransport.Leg(
                payloads = listOf(
                    """{"type":"snapshot","data":{"services":[
                        {"name":"llamacpp-a","status":"running","kind":"chat","host_port":3301,"favorite":false}
                    ],"total":1,"running":1,"stopped":0}}""",
                ),
                failWith = RuntimeException("connection reset"),
            ),
        )
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val repository = ServicesStreamRepository(transport)

        val emissions = withTimeout(5_000) { repository.streamWithStatus(reconnectDelayMs = 1L).take(2).toList() }

        assertEquals(false, emissions[0].stale)
        assertEquals(listOf(running), emissions[0].services)

        assertEquals("the drop must be surfaced, not swallowed silently", true, emissions[1].stale)
        assertEquals("the last known list is carried forward, not blanked", listOf(running), emissions[1].services)
    }
}
