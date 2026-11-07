package com.hpz.llmdockchat.feature.pi

import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.core.net.SseTransport
import com.hpz.llmdockchat.data.PiCommandsRepository
import com.hpz.llmdockchat.data.model.PiCommandOutcome
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.data.model.Rejection
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.testing.FakePiCommandsRepository
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.MainDispatcherRule
import com.hpz.llmdockchat.testing.ScriptedSseTransport
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.After
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class PiSessionViewModelTest {
    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    @get:Rule val temporary = TemporaryFolder()
    private val cacheScopes = mutableListOf<CoroutineScope>()

    private val key = PiSessionKey("s1", "i1")
    private val viewModels = mutableListOf<PiSessionViewModel>()

    @After
    fun tearDown() {
        viewModels.forEach { it.viewModelScope.cancel() }
        viewModels.clear()
        cacheScopes.forEach { it.cancel() }
    }

    private fun viewModel(
        transport: SseTransport,
        commands: PiCommandsRepository = FakePiCommandsRepository(),
        clock: () -> Long = System::currentTimeMillis,
    ): PiSessionViewModel = PiSessionViewModel(
        key,
        PiRuntimeFixture(temporary.newFolder(), CoroutineScope(SupervisorJob() + Dispatchers.Unconfined).also { cacheScopes += it }).runtime(transport),
        commands,
        clock,
    ).also { viewModels += it }

    private fun connectedTransport() = FakeSseTransport().apply { payloads = listOf(piSummary()); stayOpen = true }

    private fun eventsFrame(): String = """
        {"type":"events","events":[
            {"seq":1,"type":"user_message","ts":1000,"payload":{"text":"hi","image_count":0,"origin":"terminal"}},
            {"seq":2,"type":"assistant_delta","ts":2000,"payload":{"text":"hello","thinking":""}}
        ]}
    """.trimIndent()

    private suspend fun awaitLoaded(viewModel: PiSessionViewModel): PiSessionUiState.Loaded =
        viewModel.state.first { it is PiSessionUiState.Loaded } as PiSessionUiState.Loaded

    @Test
    fun `starts loading`() {
        val viewModel = viewModel(FakeSseTransport())
        assertTrue(viewModel.state.value is PiSessionUiState.Loading)
    }

    @Test
    fun `first emission loads transcript`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(ScriptedSseTransport.Leg(payloads = listOf(eventsFrame()), park = true))
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val viewModel = viewModel(transport)
        viewModel.start()

        val loaded = awaitLoaded(viewModel)
        assertEquals(2, loaded.transcript.items.size)
        assertTrue(loaded.transcript.items[0] is PiItem.User)
        assertTrue(loaded.transcript.items[1] is PiItem.Assistant)
        assertEquals(PiSessionPhase.CATCHING_UP, loaded.phase)
    }

    @Test
    fun `unknown maps to Unknown`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(
            ScriptedSseTransport.Leg(
                failWith = ApiException(AppError.Http(404, "unknown_session", true)),
            ),
        )
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val viewModel = viewModel(transport)
        viewModel.start()

        assertTrue(
            viewModel.state.first { it is PiSessionUiState.Unknown } is PiSessionUiState.Unknown,
        )
    }

    @Test
    fun `stale passed through`() = runTest {
        val transport = ScriptedSseTransport()
        transport.script(ScriptedSseTransport.Leg(failWith = RuntimeException("down")))
        transport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val viewModel = viewModel(transport)
        viewModel.start()

        val loaded = awaitLoaded(viewModel)
        assertTrue(loaded.stale)
        assertTrue(loaded.transcript.items.isEmpty())
    }

    @Test
    fun `start is idempotent`() = runTest {
        val transport = FakeSseTransport()
        transport.payloads = listOf(eventsFrame())
        val viewModel = viewModel(transport)
        viewModel.start()
        viewModel.start()

        awaitLoaded(viewModel)
        assertEquals(1, transport.requests.size)
    }

    @Test
    fun `send clears draft on done`() {
        val commands = FakePiCommandsRepository()
        val viewModel = viewModel(connectedTransport(), commands)
        viewModel.start()
        viewModel.onDraftChange("hello")

        viewModel.send()

        assertEquals("hello", commands.sentText)
        assertEquals("", viewModel.composerState.value.draft)
        assertNull(viewModel.composerState.value.notice)
        assertFalse(viewModel.composerState.value.sending)
    }

    @Test
    fun `send keeps draft and sets notice on rejection`() {
        val commands = FakePiCommandsRepository()
        commands.sendOutcome = PiCommandOutcome.Rejected(Rejection.OFFLINE)
        val viewModel = viewModel(connectedTransport(), commands)
        viewModel.start()
        viewModel.onDraftChange("hello")

        viewModel.send()

        assertEquals("hello", viewModel.composerState.value.draft)
        assertEquals("pi is offline", viewModel.composerState.value.notice)
        assertFalse(viewModel.composerState.value.sending)
    }

    @Test
    fun `whitespace is not sent`() {
        val commands = FakePiCommandsRepository()
        val viewModel = viewModel(connectedTransport(), commands)
        viewModel.start()
        viewModel.onDraftChange("   ")

        viewModel.send()

        assertNull(commands.sentText)
        assertEquals("   ", viewModel.composerState.value.draft)
        assertFalse(viewModel.composerState.value.sending)
    }

    @Test
    fun `stop records lastStopAt then aborts`() {
        val commands = FakePiCommandsRepository()
        val viewModel = viewModel(connectedTransport(), commands, clock = { 1000L })
        viewModel.start()

        viewModel.stop()

        assertEquals(1000L, viewModel.composerState.value.lastStopAt)
        assertTrue(commands.abortCalled)
        assertFalse(viewModel.composerState.value.stopping)
    }
}
