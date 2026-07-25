package com.hpz.llmdockchat.feature.thread

import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.hpz.llmdockchat.core.auth.Reauthenticator
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.SessionAuthenticator
import com.hpz.llmdockchat.data.ChatRepository
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.testing.FakeDraftStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.ScriptedSseTransport
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.readFixture
import com.hpz.llmdockchat.testing.quiesceAndRelease
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.IOException
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * F09 review probe — two mechanisms `ThreadReattachTest` does not assert.
 *
 * 1. A stream the server *closed* is never retried. That is what keeps Stop
 *    from starting a reconnect storm: a cancelled run emits no terminal frame
 *    at all (`_sse_frames_for` maps `run_cancelled` to nothing), so on the wire
 *    a cancel is indistinguishable from a clean completion, and both must end
 *    the loop.
 * 2. Leaving the thread stops the reconnect loop — asserted as *no further
 *    subscribe*, and as the parked connection actually being torn down, rather
 *    than as a flag going null.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadReconnectTeardownTest {

    private lateinit var server: MockWebServer
    private lateinit var transport: ScriptedSseTransport
    private lateinit var repository: ChatRepository
    private lateinit var servicesStreamRepository: ServicesStreamRepository
    private lateinit var openRouterModelsRepository: OpenRouterModelsRepository
    private lateinit var conversationsRepository: ConversationsRepository
    private lateinit var mcpServersRepository: McpServersRepository
    private val store = ViewModelStore()
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "probe-main") }

    @Before
    fun setUp() {
        Dispatchers.setMain(mainExecutor.asCoroutineDispatcher())
        server = MockWebServer()
        server.start()
        transport = ScriptedSseTransport()
        val urlStore = FakeServerUrlStore(baseUrl(server.url("/").toString()))
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .authenticator(
                SessionAuthenticator(FakeTokenStore("totp-test"), SessionState(), Reauthenticator.NoCredential),
            )
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
        repository = ChatRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO), transport)
        servicesStreamRepository = ServicesStreamRepository(FakeSseTransport())
        openRouterModelsRepository = OpenRouterModelsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        conversationsRepository = ConversationsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        mcpServersRepository = McpServersRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
    }

    @After
    fun tearDown() {
        store.clear()
        server.close()
        mainExecutor.quiesceAndRelease()
        Dispatchers.resetMain()
    }

    private fun conversation(fixture: String) =
        server.enqueue(MockResponse.Builder().body(readFixture(fixture)).build())

    private fun viewModel(backoffMs: Long = 1L): ThreadViewModel = ViewModelProvider.create(
        store,
        viewModelFactory {
            initializer {
                ThreadViewModel(
                    conversationId = CONVERSATION_ID,
                    repository = repository,
                    drafts = FakeDraftStore(),
                    servicesStreamRepository = servicesStreamRepository,
                    openRouterModelsRepository = openRouterModelsRepository,
                    conversationsRepository = conversationsRepository,
                    mcpServersRepository = mcpServersRepository,
                    coalesceWindowMs = 0,
                    titleSettleDelayMs = 1L,
                    reconnectInitialMs = backoffMs,
                    reconnectMaxMs = backoffMs,
                )
            }
        },
    )[ThreadViewModel::class]

    private suspend fun ThreadViewModel.awaitState(
        what: String,
        p: (ThreadUiState.Loaded) -> Boolean,
    ): ThreadUiState.Loaded {
        val reached = runCatching {
            withTimeout(TIMEOUT_MS) { state.first { it is ThreadUiState.Loaded && p(it) } }
        }
        return reached.getOrNull() as? ThreadUiState.Loaded
            ?: throw AssertionError("never reached: $what — last state was ${state.value}")
    }

    /**
     * Stop, as it actually arrives: the run is cancelled server-side, the
     * partial is never persisted, and the stream just *ends* — no `[DONE]`, no
     * `message_saved`, no error. A client that treated a closed stream as
     * something to reconnect to would reattach here, and would keep doing it
     * every time the user pressed Stop.
     */
    @Test
    fun `a cancelled run's silent close ends the loop instead of reattaching`() = runBlocking {
        conversation("conversation_active_run.json")
        // One leg only: the script running out would hand out a parked leg and
        // record a request, which is exactly what must not happen.
        transport.script(
            ScriptedSseTransport.Leg(payloads = listOf(RUN_STARTED, delta("half an answer"))),
        )
        // The refetch every terminal triggers; the cancelled run saved nothing,
        // so the thread comes back on the user's message alone.
        conversation("conversation_cancelled_run.json")

        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitState("the settled thread") { it.thread.streaming == null && !it.runActive }

        // Long enough for several of this ViewModel's 1 ms backoff steps.
        delay(300)
        assertEquals(
            "a clean close was retried — every Stop would start a reconnect loop",
            1,
            transport.requests.size,
        )
    }

    /**
     * Leaving the thread while the connection is up. The mechanism, not a flag:
     * the parked leg's `finally` runs, which only happens if the collector was
     * actually cancelled, and nothing subscribes again afterwards.
     */
    @Test
    fun `leaving the thread tears the live connection down and never resubscribes`() = runBlocking {
        conversation("conversation_active_run.json")
        val live = ScriptedSseTransport.Leg(payloads = listOf(RUN_STARTED, delta("mid answer")), park = true)
        transport.script(live)

        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitState("the replay") { it.thread.streaming?.content == "mid answer" }

        store.clear() // what leaving the screen does: onCleared -> viewModelScope cancelled

        withTimeout(TIMEOUT_MS) { live.cancelled.await() }
        delay(300)
        assertEquals("something resubscribed after the screen went away", 1, transport.requests.size)
    }

    /**
     * The same, but caught mid-*backoff* — the state F07's bug lived in, where a
     * swallowed cancellation left a retry loop running with nothing on screen.
     * The wait here is 400 ms per attempt, so the loop is certainly parked in
     * `delay` when the ViewModel is cleared.
     */
    @Test
    fun `leaving the thread during a reconnect wait stops the retry loop`() = runBlocking {
        conversation("conversation_active_run.json")
        val dropped = ApiException(AppError.Network(IOException("unexpected end of stream")))
        transport.script(
            ScriptedSseTransport.Leg(payloads = listOf(RUN_STARTED, delta("half")), failWith = dropped),
        )
        // Anything the loop asks for after this is a leg from whenScriptRunsOut,
        // and every one of them is counted.
        val viewModel = viewModel(backoffMs = 400L)
        viewModel.load()
        viewModel.awaitState("the reconnecting state") { it.thread.streaming?.reconnecting == true }

        store.clear()
        val subscribesAtTeardown = transport.requests.size

        delay(1_500) // ~3 backoff periods
        assertEquals(
            "the reconnect loop outlived the screen",
            subscribesAtTeardown,
            transport.requests.size,
        )
        assertTrue("precondition: the drop happened while subscribed", subscribesAtTeardown >= 1)
    }

    private companion object {
        const val TIMEOUT_MS = 10_000L
        const val CONVERSATION_ID = "ac743d66-9611-4b48-9bf3-df25df79f81e"
        const val RUN_STARTED = """{"type": "run_started", "run_id": "run-1"}"""

        fun delta(text: String) = """{"choices":[{"index":0,"delta":{"content":"$text"}}]}"""
    }
}
