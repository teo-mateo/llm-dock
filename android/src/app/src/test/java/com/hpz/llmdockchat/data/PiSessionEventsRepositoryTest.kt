package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.data.model.PiEvent
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.ScriptedSseTransport
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class PiSessionEventsRepositoryTest {

    private val key = PiSessionKey("s1", "i1")

    private fun eventJson(seq: Long): String =
        """{"seq":$seq,"type":"message","ts":${seq * 100},"payload":{"text":"e$seq"}}"""

    private fun eventsFrame(vararg seqs: Long): String =
        """{"type":"events","events":[${seqs.joinToString(",") { eventJson(it) }}]}"""

    private fun sessionFrame(): String = """
        {"type":"session","session_id":"s1","instance_id":"i1","name":"llm-dock",
         "cwd":"/repo","model":"mistral/small","thinking_level":"high",
         "first_seen":1000,"last_seen":2000,"ended_at":null,"end_reason":null,
         "live":true,"state":"working","context_percent":22.5}
    """.trimIndent()

    private fun event(seq: Long): PiEvent =
        PiEvent(seq, "message", seq * 100, kotlinx.serialization.json.JsonObject(emptyMap()))

    @Test
    fun `first connect sends after 0`() = runTest {
        val transport = FakeSseTransport()
        transport.payloads = listOf(eventsFrame(1))
        val repository = PiSessionEventsRepository(transport)

        val states = withTimeout(5_000) {
            repository.stream(key, reconnectDelayMs = 1L).take(1).toList()
        }

        assertFalse(states.single().stale)
        assertEquals(listOf(1L), states.single().appended.map { it.seq })
        assertEquals(Endpoints.piSessionStream("s1", "i1"), transport.requests[0].path)
        assertEquals("0", transport.requests[0].query["after"])
    }

    @Test
    fun `reconnect sends after last seq`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(
            ScriptedSseTransport.Leg(payloads = listOf(eventsFrame(1, 2))),
            ScriptedSseTransport.Leg(payloads = listOf(eventsFrame(3))),
        )
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val repository = PiSessionEventsRepository(transport)

        val states = withTimeout(5_000) {
            repository.stream(key, reconnectDelayMs = 1L).take(3).toList()
        }

        assertFalse(states[0].stale)
        assertEquals(listOf(1L, 2L), states[0].appended.map { it.seq })
        assertTrue(states[1].stale)
        assertFalse(states[2].stale)
        assertEquals(listOf(3L), states[2].appended.map { it.seq })
        assertTrue(states[1].appended.isEmpty())
        assertEquals(listOf(2L, 2L, 3L), states.map { it.lastSeq })
        assertEquals("2", transport.requests[1].query["after"])
    }

    @Test
    fun `duplicates and older seqs are dropped`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(
            ScriptedSseTransport.Leg(
                payloads = listOf(eventsFrame(1, 2)),
                failWith = RuntimeException("down"),
            ),
            ScriptedSseTransport.Leg(payloads = listOf(eventsFrame(2, 3, 1, 4))),
        )
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val repository = PiSessionEventsRepository(transport)

        val states = withTimeout(5_000) {
            repository.stream(key, reconnectDelayMs = 1L).take(3).toList()
        }

        assertEquals(listOf(3L, 4L), states[2].appended.map { it.seq })
    }

    @Test
    fun `fresh batch sorts and drops duplicates and older seqs`() {
        val incoming = listOf(event(2), event(4), event(3), event(1), event(4))
        assertEquals(listOf(3L, 4L), freshPiSessionEvents(2, incoming).map { it.seq })
    }

    @Test
    fun `session frame sets summary`() = runTest {
        val transport = FakeSseTransport()
        transport.payloads = listOf(eventsFrame(1), sessionFrame())
        val repository = PiSessionEventsRepository(transport)

        val states = withTimeout(5_000) {
            repository.stream(key, reconnectDelayMs = 1L).take(2).toList()
        }

        assertNull(states[0].summary)
        assertTrue(states[1].appended.isEmpty())
        assertEquals(1L, states[1].lastSeq)
        assertEquals("llm-dock", states[1].summary?.name)
        assertEquals("mistral/small", states[1].summary?.model)
        assertEquals(22.5, states[1].summary?.contextPercent!!, 0.0)
    }

    @Test
    fun `lagged reconnects without delay and cannot skip unaccepted events`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(
            ScriptedSseTransport.Leg(payloads = listOf("""{"type":"lagged","after":5}""")),
            ScriptedSseTransport.Leg(payloads = listOf(eventsFrame(6))),
        )
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val repository = PiSessionEventsRepository(transport)

        val states = withTimeout(5_000) {
            repository.stream(key, reconnectDelayMs = 60_000L).filter { it.appended.isNotEmpty() }.take(1).toList()
        }

        assertEquals(listOf(6L), states.single().appended.map { it.seq })
        assertEquals(2, transport.requests.size)
        assertEquals("0", transport.requests[1].query["after"])
    }

    @Test
    fun `404 sets unknown and stops`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(
            ScriptedSseTransport.Leg(
                failWith = ApiException(AppError.Http(404, "unknown_session", true)),
            ),
        )
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val repository = PiSessionEventsRepository(transport)

        val states = repository.stream(key).toList()

        assertEquals(1, states.size)
        assertTrue(states.single().unknown)
        assertFalse(states.single().stale)
        assertEquals(1, transport.requests.size)
    }

    @Test
    fun `failure marks stale then recovers`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(
            ScriptedSseTransport.Leg(failWith = RuntimeException("down")),
            ScriptedSseTransport.Leg(payloads = listOf(eventsFrame(1))),
        )
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val repository = PiSessionEventsRepository(transport)

        val states = withTimeout(5_000) {
            repository.stream(key, reconnectDelayMs = 1L).take(2).toList()
        }

        assertTrue(states[0].stale)
        assertTrue(states[0].appended.isEmpty())
        assertFalse(states[1].stale)
        assertEquals(listOf(1L), states[1].appended.map { it.seq })
    }

    @Test
    fun `cancellation is not retried`() = runTest {
        val transport = FakeSseTransport().apply { stayOpen = true }
        val repository = PiSessionEventsRepository(transport)
        val job = launch {
            repository.stream(key, reconnectDelayMs = 1L).collect { }
        }
        runCurrent()
        job.cancel()
        job.join()

        assertTrue(transport.cancelled.isCompleted)
        assertEquals(1, transport.requests.size)
    }
}
