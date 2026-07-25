package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.ReconnectBackoff
import com.hpz.llmdockchat.data.model.GpuState
import com.hpz.llmdockchat.testing.FakeSseTransport
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * [GpuStreamRepository.stream] — the transport wiring and the
 * available/unavailable mapping (F10-R3). The teardown test is the one that
 * matters most here: F10-R3's third criterion is "closing the tab stops the
 * stream", and a test that only checks a UI flag would prove nothing — see
 * `ThreadReconnectTeardownTest` and `OkHttpSseTransportTest`'s "abandoning a
 * quiet stream" for the same pattern on other streams.
 */
class GpuStreamRepositoryTest {

    @Test
    fun `stream opens unavailable, then available once a frame with gpus lands`() = runTest {
        val transport = FakeSseTransport()
        transport.payloads = listOf(
            """{"gpus": [{"index": 0, "name": "RTX PRO 6000", "memory": {"total": 97887, "used": 61440},
                "temperature": {"current": 71}, "utilization": {"gpu_percent": 84},
                "power": {"draw": 318.0, "limit": {"enforced": 300.0}}}]}""",
        )
        val repository = GpuStreamRepository(transport)

        val emissions = withTimeout(5_000) { repository.stream().take(2).toList() }

        assertTrue("first emission is unavailable before any frame arrives", emissions[0] is GpuState.Unavailable)
        val available = emissions[1] as GpuState.Available
        assertEquals(1, available.gpus.size)
        assertEquals(61440, available.gpus[0].memoryUsedMiB)
        assertEquals(97887, available.gpus[0].memoryTotalMiB)
        assertEquals(84, available.gpus[0].utilizationPercent)
        assertEquals(71, available.gpus[0].temperatureC)
    }

    @Test
    fun `an empty gpus list is treated as unavailable, not an available card with nothing in it`() = runTest {
        val transport = FakeSseTransport()
        transport.payloads = listOf("""{"gpus": []}""")
        val repository = GpuStreamRepository(transport)

        val emissions = withTimeout(5_000) { repository.stream().take(2).toList() }

        assertTrue(emissions[0] is GpuState.Unavailable)
        assertTrue(emissions[1] is GpuState.Unavailable)
    }

    @Test
    fun `an error tick is surfaced as unavailable with the server's message`() = runTest {
        val transport = FakeSseTransport()
        transport.payloads = listOf("""{"error": "nvidia-smi command failed"}""")
        val repository = GpuStreamRepository(transport)

        val emissions = withTimeout(5_000) { repository.stream().take(2).toList() }

        assertEquals(GpuState.Unavailable("nvidia-smi command failed"), emissions[1])
    }

    /**
     * The mechanism, not a flag: a collector going away must actually cancel
     * the underlying [com.hpz.llmdockchat.core.net.SseTransport.open] call.
     * [FakeSseTransport.cancelled] only completes if the fake's flow was
     * really cancelled, which only happens if [Job.cancel] genuinely
     * propagates through [GpuStreamRepository.stream]'s reconnect loop — a
     * fake that "completed on its own" (F09's post-mortem on the F07 bug)
     * would let this pass without proving anything.
     */
    @Test
    fun `cancelling the collector actually tears down the open connection`() = runTest {
        val transport = FakeSseTransport()
        transport.stayOpen = true
        val repository = GpuStreamRepository(transport)

        val job: Job = launch { repository.stream().collect { } }
        withTimeout(5_000) { transport.parked.await() }

        job.cancel()
        withTimeout(5_000) { transport.cancelled.await() }
    }

    @Test
    fun `a dropped connection keeps retrying rather than giving up after the first attempt`() = runTest {
        val transport = FakeSseTransport()
        transport.failWith = RuntimeException("connection reset")
        val backoff = ReconnectBackoff(initialMs = 1L, maxMs = 1L)
        val repository = GpuStreamRepository(transport)

        // Every failed attempt is caught and re-emitted as Unavailable before
        // the next retry, so four emissions (the initial one plus three
        // failed attempts) is proof of three separate `open()` calls —
        // no busy-wait needed, same `take(n).toList()` idiom as the rest of
        // this suite.
        withTimeout(5_000) { repository.stream(backoff = backoff).take(4).toList() }

        assertEquals(3, transport.requests.size)
    }
}
