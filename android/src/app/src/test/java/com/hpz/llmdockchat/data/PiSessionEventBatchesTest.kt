package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.feature.pi.transcript.TranscriptBuilder
import com.hpz.llmdockchat.feature.pi.transcript.buildPiTranscript
import com.hpz.llmdockchat.testing.ScriptedSseTransport
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.buffer
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class PiSessionEventBatchesTest {
    private val key = PiSessionKey("s1", "i1")

    private fun batch(vararg seqs: Long): String =
        """{"type":"events","events":[${seqs.joinToString(",") {
            """{"seq":$it,"type":"assistant_delta","ts":$it,"payload":{"text":"$it,"}}"""
        }}]}"""

    @Test
    fun `seed resumes first request and second positional argument remains retry delay`() = runTest {
        val transport = ScriptedSseTransport().script(
            ScriptedSseTransport.Leg(payloads = listOf(batch(10, 12, 12, 11))),
            ScriptedSseTransport.Leg(payloads = listOf(batch(12, 20))),
        )
        val states = PiSessionEventsRepository(transport).stream(key, 123L, after = 10L).take(3).toList()
        assertEquals(listOf("10", "12"), transport.requests.map { it.query["after"] })
        assertEquals(123L, currentTime)
        assertEquals(listOf(11L, 12L), states[0].appended.map { it.seq })
        assertTrue(states[1].appended.isEmpty())
        assertEquals(listOf(20L), states[2].appended.map { it.seq })
        assertEquals(listOf(12L, 12L, 20L), states.map { it.lastSeq })
    }

    @Test
    fun `lagged hints never advance or rewind accepted cursor`() = runTest {
        for (hint in listOf(1L, 5L, 500L)) {
            val transport = ScriptedSseTransport().script(
                ScriptedSseTransport.Leg(payloads = listOf(batch(5), """{"type":"lagged","after":$hint}""")),
                ScriptedSseTransport.Leg(payloads = listOf(batch(5, 9))),
            )
            val states = PiSessionEventsRepository(transport).stream(key, 60_000L).filter { it.appended.isNotEmpty() }.take(2).toList()
            assertEquals("5", transport.requests[1].query["after"])
            assertEquals(listOf(5L, 9L), states.flatMap { it.appended }.map { it.seq })
            assertEquals(0L, currentTime)
        }
    }

    @Test
    fun `slow collector receives every fresh batch exactly once`() = runTest {
        val transport = ScriptedSseTransport().script(
            ScriptedSseTransport.Leg(payloads = (1L..200L).map { batch(it - 1, it, it) }),
        )
        val builder = TranscriptBuilder()
        val states = mutableListOf<PiSessionEventsState>()
        PiSessionEventsRepository(transport).stream(key).buffer(1).take(200).collect { state ->
            delay(10)
            state.appended.forEach { builder.apply(it) }
            states += state
        }
        assertEquals((1L..200L).toList(), states.flatMap { it.appended }.map { it.seq })
        assertEquals((1L..200L).toList(), states.map { it.lastSeq })
        assertEquals(buildPiTranscript(states.flatMap { it.appended }), builder.transcript())
        assertEquals(1, transport.requests.size)
    }

    @Test
    fun `removed after a batch is terminal even if transport stays open`() = runTest {
        val transport = ScriptedSseTransport().script(
            ScriptedSseTransport.Leg(
                payloads = listOf(batch(7), """{"type":"session_removed","session_id":"s1","instance_id":"i1"}""", batch(8)),
                park = true,
            ),
        )
        val states = PiSessionEventsRepository(transport).stream(key).toList()
        assertEquals(2, states.size)
        assertEquals(listOf(7L), states[0].appended.map { it.seq })
        assertTrue(states[1].unknown)
        assertFalse(states[1].stale)
        assertTrue(states[1].appended.isEmpty())
        assertEquals(7L, states[1].lastSeq)
        assertEquals(1, transport.requests.size)
    }

    @Test
    fun `removal of another identity is ignored`() = runTest {
        val transport = ScriptedSseTransport().script(
            ScriptedSseTransport.Leg(payloads = listOf(
                """{"type":"session_removed","session_id":"other","instance_id":"i1"}""",
                """{"type":"session_removed","session_id":"s1","instance_id":"other"}""",
                batch(1),
            )),
        )
        val state = PiSessionEventsRepository(transport).stream(key).take(1).toList().single()
        assertFalse(state.unknown)
        assertEquals(1L, state.lastSeq)
    }

    @Test
    fun `404 after a batch reports no repeated data and stops`() = runTest {
        val transport = ScriptedSseTransport().script(
            ScriptedSseTransport.Leg(payloads = listOf(batch(4)), failWith = ApiException(AppError.Http(404, "unknown_session", true))),
        )
        val states = PiSessionEventsRepository(transport).stream(key).toList()
        assertEquals(2, states.size)
        assertTrue(states[1].unknown)
        assertTrue(states[1].appended.isEmpty())
        assertEquals(4L, states[1].lastSeq)
        assertEquals(1, transport.requests.size)
    }

    @Test
    fun `transport cancellation propagates without stale emission or retry`() = runTest {
        val cancelled = CancellationException("cancelled")
        val transport = ScriptedSseTransport().script(
            ScriptedSseTransport.Leg(payloads = listOf(batch(1)), failWith = cancelled),
        )
        val states = mutableListOf<PiSessionEventsState>()
        val result = runCatching { PiSessionEventsRepository(transport).stream(key).toList(states) }
        assertTrue(result.exceptionOrNull() === cancelled)
        assertEquals(1, states.size)
        assertFalse(states.single().stale)
        assertEquals(1, transport.requests.size)
    }

    @Test
    fun `negative seed is rejected before opening transport`() = runTest {
        val transport = ScriptedSseTransport()
        val result = runCatching { PiSessionEventsRepository(transport).stream(key, after = -1).toList() }
        assertTrue(result.exceptionOrNull() is IllegalArgumentException)
        assertTrue(transport.requests.isEmpty())
    }
}
