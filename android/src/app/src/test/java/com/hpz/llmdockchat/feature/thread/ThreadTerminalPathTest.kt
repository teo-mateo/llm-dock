package com.hpz.llmdockchat.feature.thread

import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.hpz.llmdockchat.core.auth.Reauthenticator
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
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
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.CoroutineScope
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
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * What the end of a run leaves on screen.
 *
 * Every terminal refetches and drops `streaming` (Architecture D3), which is
 * right up to the point where the refetch itself fails: the server's copy is
 * then unreachable and dropping the turn would take the whole exchange —
 * answer, error and the user's own message — off screen with nothing said. So
 * the turn is held over instead, marked unconfirmed, until a load succeeds.
 *
 * These three cases came out of the F04 review; they are here rather than in
 * [ThreadViewModelTest] because F09's reattach lands on the same terminal path.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadTerminalPathTest {

    private lateinit var server: MockWebServer
    private lateinit var transport: FakeSseTransport
    private lateinit var repository: ChatRepository
    private lateinit var servicesStreamRepository: ServicesStreamRepository
    private lateinit var openRouterModelsRepository: OpenRouterModelsRepository
    private lateinit var conversationsRepository: ConversationsRepository
    private lateinit var mcpServersRepository: McpServersRepository
    private val store = ViewModelStore()
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "terminal-main") }

    @Before
    fun setUp() {
        Dispatchers.setMain(mainExecutor.asCoroutineDispatcher())
        server = MockWebServer()
        server.start()
        transport = FakeSseTransport()
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
        Dispatchers.resetMain()
        mainExecutor.shutdownNow()
    }

    private fun conversation(fixture: String = "conversation_completed.json") =
        server.enqueue(MockResponse.Builder().body(readFixture(fixture)).build())

    private fun serverError(code: Int = 500) =
        server.enqueue(MockResponse.Builder().code(code).body("""{"error":"boom"}""").build())

    private fun viewModel(): ThreadViewModel = ViewModelProvider.create(
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
                )
            }
        },
    )[ThreadViewModel::class]

    private fun threadTest(body: suspend CoroutineScope.() -> Unit) = runBlocking { body() }

    private suspend fun ThreadViewModel.awaitLoaded() =
        withTimeout(10_000) { state.first { it is ThreadUiState.Loaded } as ThreadUiState.Loaded }

    private suspend fun ThreadViewModel.awaitState(p: (ThreadUiState.Loaded) -> Boolean) =
        withTimeout(10_000) { state.first { it is ThreadUiState.Loaded && p(it) } as ThreadUiState.Loaded }

    /**
     * The turn completed and the server saved it, but the refetch that would
     * bring it back fails. The answer stays where it is, the run reads as over,
     * and the failure is reported — and the moment a load does succeed, the
     * held-over turn gives way to the saved message rather than doubling it.
     */
    @Test
    fun `a failed refetch after message_saved keeps the turn and says what went wrong`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED, delta("hello"), DONE, MESSAGE_SAVED)
        serverError() // the refetch every terminal triggers
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()

        val held = viewModel.awaitState { it.thread.streaming?.unconfirmed == true }
        assertEquals("hello", held.thread.streaming?.content)
        assertEquals("hi", held.thread.streaming?.userMessage?.content)
        assertNotNull("the refetch failure was not surfaced", held.actionError)
        // Over, not still running: the composer has to come back.
        assertFalse(held.runActive)

        conversation()
        viewModel.load()
        val settled = viewModel.awaitState { it.thread.streaming == null }
        assertEquals(2, settled.thread.messages.size)
    }

    /** Same on the failure path, where the held-over text is the persisted partial. */
    @Test
    fun `a failed refetch after an error frame keeps the partial and its error`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED, delta("part"), ERROR_FRAME)
        serverError()
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()

        val held = viewModel.awaitState { it.thread.streaming?.unconfirmed == true }
        assertEquals("part", held.thread.streaming?.content)
        assertEquals(ERROR_TEXT, held.thread.streaming?.error)
        assertEquals(ERROR_TEXT, held.actionError)
        assertFalse(held.runActive)
    }

    /**
     * Every state the UI observes between the last delta and the settled thread
     * must show the answer somewhere — as `streaming` or in `messages` — and it
     * must show all of it. The last coalescing window is flushed before the
     * refetch, so the tail is not missing for the length of a round trip.
     */
    @Test
    fun `the whole answer stays on screen for the length of the refetch`() = threadTest {
        conversation()
        transport.payloads = listOf(RUN_STARTED, delta("hello"), DONE, MESSAGE_SAVED)
        // A slow refetch widens the window in which the terminal path could
        // blank the screen, so the check is deterministic rather than a race.
        server.enqueue(
            MockResponse.Builder()
                .body(readFixture("conversation_completed.json"))
                .bodyDelay(700, TimeUnit.MILLISECONDS)
                .build(),
        )
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("hi")
        viewModel.send()

        // Mid-refetch: whatever is on screen now is what the user sees for the
        // next half second.
        delay(350)
        val midRefetch = viewModel.state.value as ThreadUiState.Loaded
        assertNotNull("the streaming turn was dropped before the refetch returned", midRefetch.thread.streaming)
        assertEquals("the tail of the answer was lost", "hello", midRefetch.thread.streaming?.content)

        val settled = viewModel.awaitState { it.thread.streaming == null && it.thread.messages.size == 2 }
        assertTrue(settled.thread.messages.last().content.isNotBlank())
    }

    private companion object {
        const val CONVERSATION_ID = "39dc7f47-91da-4a0f-b731-59f507a12c1b"
        const val RUN_STARTED = """{"type": "run_started", "run_id": "run-1"}"""
        const val DONE = "[DONE]"
        const val MESSAGE_SAVED = """{"type": "message_saved", "message_id": "m2", "seq": 2}"""
        const val ERROR_TEXT = "Service 'x' is not reachable. Is it running?"
        const val ERROR_FRAME = """{"error": "$ERROR_TEXT"}"""

        fun delta(text: String) = """{"choices":[{"index":0,"delta":{"content":"$text"}}]}"""
    }
}
