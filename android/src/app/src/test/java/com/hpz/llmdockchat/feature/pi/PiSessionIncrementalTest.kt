package com.hpz.llmdockchat.feature.pi

import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.testing.FakePiCommandsRepository
import com.hpz.llmdockchat.testing.MainDispatcherRule
import com.hpz.llmdockchat.testing.ScriptedSseTransport
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

@OptIn(ExperimentalCoroutinesApi::class)
class PiSessionIncrementalTest {
    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    @get:Rule val temporary = TemporaryFolder()

    private val replay = """{"type":"events","events":[
        {"seq":1,"type":"assistant_delta","ts":1,"payload":{"text":"A"}},
        {"seq":2,"type":"compaction","ts":2,"payload":{}},
        {"seq":3,"type":"state","ts":3,"payload":{"state":"working"}}
    ]}"""
    private val summary = """{"type":"session","session_id":"s","instance_id":"i",
        "name":"session","cwd":"/repo","first_seen":1,"last_seen":2,"live":true,"state":"working"}"""
    private val removed = """{"type":"session_removed","session_id":"s","instance_id":"i"}"""

    private fun delta(seq: Long, text: String) = """{"type":"events","events":[
        {"seq":$seq,"type":"assistant_delta","ts":$seq,"payload":{"text":"$text"}}
    ]}"""

    @Test
    fun `worker applies batches once and reuses transcript for metadata and stale updates`() = runTest {
        val summaryGate = CompletableDeferred<Unit>()
        val failureGate = CompletableDeferred<Unit>()
        val removalGate = CompletableDeferred<Unit>()
        val transport = ScriptedSseTransport().script(
            ScriptedSseTransport.Leg(
                payloads = listOf(replay, delta(4, "B"), delta(4, "duplicate")),
                endGate = summaryGate,
                tailPayloads = listOf(summary),
            ),
            ScriptedSseTransport.Leg(
                openGate = failureGate,
                failWith = RuntimeException("offline"),
            ),
            ScriptedSseTransport.Leg(
                payloads = listOf(delta(4, "overlap"), delta(8, "C")),
                endGate = removalGate,
                tailPayloads = listOf(removed, delta(9, "must not apply")),
                park = true,
            ),
        )
        val viewModel = PiSessionViewModel(
            PiSessionKey("s", "i"),
            PiRuntimeFixture(temporary.newFolder(), backgroundScope, StandardTestDispatcher(testScheduler))
                .runtime(transport, PiSessionKey("s", "i")),
            FakePiCommandsRepository(),
        )
        try {
            viewModel.start()
            viewModel.start()
            assertSame(PiSessionUiState.Loading, viewModel.state.value)
            assertTrue(transport.requests.isEmpty())
            runCurrent()
            val replayed = viewModel.state.value as PiSessionUiState.Loaded
            assertEquals("AB", (replayed.transcript.items[0] as PiItem.Assistant).text)
            assertTrue(replayed.transcript.items[1] is PiItem.Notice)
            assertTrue(replayed.transcript.working)
            assertEquals(1, transport.requests.size)

            summaryGate.complete(Unit)
            runCurrent()
            val withSummary = viewModel.state.value as PiSessionUiState.Loaded
            assertEquals("session", withSummary.summary?.name)
            assertSame(replayed.transcript, withSummary.transcript)
            assertTrue(withSummary.stale)

            advanceTimeBy(3_000)
            runCurrent()
            failureGate.complete(Unit)
            runCurrent()
            val stale = viewModel.state.value as PiSessionUiState.Loaded
            assertTrue(stale.stale)
            assertSame(replayed.transcript, stale.transcript)

            advanceTimeBy(3_000)
            runCurrent()
            val live = viewModel.state.value as PiSessionUiState.Loaded
            assertEquals("ABC", (live.transcript.items[0] as PiItem.Assistant).text)
            assertEquals("AB", (replayed.transcript.items[0] as PiItem.Assistant).text)
            assertEquals(listOf("0", "4", "4"), transport.requests.map { it.query["after"] })

            removalGate.complete(Unit)
            runCurrent()
            assertSame(PiSessionUiState.Unknown, viewModel.state.value)
            advanceTimeBy(60_000)
            runCurrent()
            assertEquals(3, transport.requests.size)
        } finally {
            viewModel.viewModelScope.cancel()
        }
    }

    @Test
    fun `cancelling queued worker prevents stream start or publication`() = runTest {
        val transport = ScriptedSseTransport().script(
            ScriptedSseTransport.Leg(payloads = listOf(replay)),
        )
        val viewModel = PiSessionViewModel(
            PiSessionKey("s", "i"),
            PiRuntimeFixture(temporary.newFolder(), backgroundScope, StandardTestDispatcher(testScheduler))
                .runtime(transport, PiSessionKey("s", "i")),
            FakePiCommandsRepository(),
        )
        viewModel.start()
        viewModel.viewModelScope.cancel()
        runCurrent()
        assertTrue(transport.requests.isEmpty())
        assertSame(PiSessionUiState.Loading, viewModel.state.value)
    }
}
