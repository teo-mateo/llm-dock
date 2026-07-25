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
import com.hpz.llmdockchat.data.PromptsRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.testing.FakeDraftStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.quiesceAndRelease
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * The "tools for this chat" sheet (F08) — the in-thread half of F03-R3's
 * server list, and the toggle-with-optimistic-revert shape that
 * `mcp_servers`/`mcp_servers_json`'s read/write asymmetry (Architecture D6)
 * forces on every write here.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadToolsTest {

    private lateinit var server: MockWebServer
    private lateinit var transport: FakeSseTransport
    private lateinit var drafts: FakeDraftStore
    private lateinit var repository: ChatRepository
    private lateinit var servicesStreamRepository: ServicesStreamRepository
    private lateinit var openRouterModelsRepository: OpenRouterModelsRepository
    private lateinit var conversationsApi: ApiClient
    private lateinit var conversationsRepository: ConversationsRepository
    private lateinit var mcpServersRepository: McpServersRepository
    private lateinit var promptsRepository: PromptsRepository
    private val store = ViewModelStore()
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "tools-main") }

    @Before
    fun setUp() {
        Dispatchers.setMain(mainExecutor.asCoroutineDispatcher())
        server = MockWebServer()
        server.start()
        transport = FakeSseTransport()
        drafts = FakeDraftStore()
        val urlStore = FakeServerUrlStore(baseUrl(server.url("/").toString()))
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .authenticator(SessionAuthenticator(FakeTokenStore("totp-test"), SessionState(), Reauthenticator.NoCredential))
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
        repository = ChatRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO), transport)
        servicesStreamRepository = ServicesStreamRepository(FakeSseTransport())
        openRouterModelsRepository = OpenRouterModelsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        conversationsApi = ApiClient(client, urlStore, ApiJson, Dispatchers.IO)
        conversationsRepository = ConversationsRepository(conversationsApi)
        mcpServersRepository = McpServersRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        promptsRepository = PromptsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
    }

    @After
    fun tearDown() {
        store.clear()
        server.close()
        mainExecutor.quiesceAndRelease()
        Dispatchers.resetMain()
    }

    private fun conversation(fixture: String = "conversation_completed.json") =
        server.enqueue(MockResponse.Builder().body(readFixture(fixture)).build())

    private fun mcpServers() =
        server.enqueue(MockResponse.Builder().body(readFixture("mcp_servers.json")).build())

    private fun viewModel(
        conversations: ConversationsRepository = conversationsRepository,
    ): ThreadViewModel = ViewModelProvider.create(
        store,
        viewModelFactory {
            initializer {
                ThreadViewModel(
                    conversationId = CONVERSATION_ID,
                    repository = repository,
                    drafts = drafts,
                    servicesStreamRepository = servicesStreamRepository,
                    openRouterModelsRepository = openRouterModelsRepository,
                    conversationsRepository = conversations,
                    mcpServersRepository = mcpServersRepository,
                    promptsRepository = promptsRepository,
                    coalesceWindowMs = 0,
                    titleSettleDelayMs = 1,
                )
            }
        },
    )[ThreadViewModel::class]

    private fun threadTest(body: suspend CoroutineScope.() -> Unit) = runBlocking { body() }

    /**
     * Runs the main dispatcher's queue dry. [mainExecutor] is single-threaded
     * and FIFO, so a task submitted now cannot finish before everything queued
     * ahead of it has run to its next suspension point — which makes "has the
     * next write gone out yet?" a settled question rather than a race.
     */
    private fun drainMain() {
        mainExecutor.submit { }.get(10, TimeUnit.SECONDS)
    }

    private suspend fun ThreadViewModel.awaitLoaded(): ThreadUiState.Loaded =
        withTimeout(10_000) { state.first { it is ThreadUiState.Loaded } as ThreadUiState.Loaded }

    private suspend fun ThreadViewModel.awaitState(
        predicate: (ThreadUiState.Loaded) -> Boolean,
    ): ThreadUiState.Loaded = withTimeout(10_000) {
        state.first { it is ThreadUiState.Loaded && predicate(it) } as ThreadUiState.Loaded
    }

    // -- F08-R1 · listing --------------------------------------------------

    @Test
    fun `openSettings fetches the registry and populates the sheet`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()

        mcpServers()
        viewModel.openSettings()

        val state = viewModel.awaitState { it.settings?.servers?.isNotEmpty() == true }
        assertEquals(8, state.settings?.servers?.size)
        assertEquals("sympy-math", state.settings?.servers?.first()?.id)
    }

    @Test
    fun `closeSettings dismisses the sheet`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()

        mcpServers()
        viewModel.openSettings()
        viewModel.awaitState { it.settings != null }

        viewModel.closeSettings()
        assertNull((viewModel.state.value as ThreadUiState.Loaded).settings)
    }

    @Test
    fun `settings still opens during a run, with the tool rows disabled`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("go")
        transport.payloads = listOf(RUN_STARTED)
        transport.stayOpen = true
        viewModel.send()
        viewModel.awaitState { it.runActive }

        mcpServers()
        viewModel.openSettings()
        val state = viewModel.awaitState { it.settings != null }

        // The sheet opens — it also holds the text-size control, which has
        // nothing to do with the run. F08-R4's actual guarantee is that a
        // toggle cannot race the turn in flight, and that is enforced in
        // `toggleTool` (see the refusal test below), not by hiding the sheet.
        assertEquals(false, state.canToggleTools)
    }

    // -- F08-R2 · toggle persists, with optimistic revert on failure -------

    @Test
    fun `toggling an unset server PUTs mcp_servers_json and reflects it immediately`() = threadTest {
        conversation() // mcp_servers: []
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()

        server.enqueue(MockResponse.Builder().body("""{"id": "$CONVERSATION_ID"}""").build())
        viewModel.toggleTool("sympy-math")

        val state = viewModel.awaitState { "sympy-math" in it.conversation.mcpServers }
        assertEquals(listOf("sympy-math"), state.conversation.mcpServers)

        server.takeRequest() // load()'s own GET, issued first
        val put = server.takeRequest()
        assertEquals("PUT", put.method)
        assertEquals("""{"mcp_servers_json":"[\"sympy-math\"]"}""", put.body?.utf8())
    }

    @Test
    fun `toggling an already-enabled server removes it and PUTs the shorter array`() = threadTest {
        conversation("conversation_tool_calls.json") // recorded with tools already enabled
        val viewModel = viewModel()
        viewModel.load()
        val loaded = viewModel.awaitLoaded()
        val enabled = loaded.conversation.mcpServers
        assertTrue("fixture must already carry an enabled server for this test", enabled.isNotEmpty())
        val target = enabled.first()

        server.enqueue(MockResponse.Builder().body("""{"id": "$CONVERSATION_ID"}""").build())
        viewModel.toggleTool(target)

        val state = viewModel.awaitState { target !in it.conversation.mcpServers }
        assertFalse(target in state.conversation.mcpServers)
    }

    @Test
    fun `toggling several servers before closing the sheet persists all of them`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()

        server.enqueue(MockResponse.Builder().body("""{"id": "$CONVERSATION_ID"}""").build())
        viewModel.toggleTool("sympy-math")
        viewModel.awaitState { it.conversation.mcpServers == listOf("sympy-math") }

        server.enqueue(MockResponse.Builder().body("""{"id": "$CONVERSATION_ID"}""").build())
        viewModel.toggleTool("websearch")

        val state = viewModel.awaitState { it.conversation.mcpServers.toSet() == setOf("sympy-math", "websearch") }
        assertEquals(2, state.conversation.mcpServers.size)

        server.takeRequest() // the load
        val firstPut = server.takeRequest()
        assertEquals("""{"mcp_servers_json":"[\"sympy-math\"]"}""", firstPut.body?.utf8())
        val secondPut = server.takeRequest()
        assertEquals("""{"mcp_servers_json":"[\"sympy-math\",\"websearch\"]"}""", secondPut.body?.utf8())
    }

    @Test
    fun `a failed write reverts the toggle and surfaces the server's message`() = threadTest {
        conversation() // mcp_servers: []
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()

        server.enqueue(
            MockResponse.Builder().code(500).body("""{"error": "Conversation not found"}""").build(),
        )
        viewModel.toggleTool("sympy-math")

        val state = viewModel.awaitState { it.actionError != null }
        assertEquals("Conversation not found", state.actionError)
        // The failed write must not leave the UI claiming a state the server
        // doesn't have — the toggle reverts to what it was before.
        assertTrue(state.conversation.mcpServers.isEmpty())
    }

    /**
     * The lost-update race the sheet was shipped with. Every toggle PUTs the
     * whole array, so two writes outstanding at once is a last-writer-wins
     * fight the *earlier* one can win — which is how a server ended up
     * holding a selection the user had already moved past, and how a tool
     * they never tapped appeared to switch itself on.
     *
     * Nothing here waits on the clock: the fake parks each write on its own
     * gate and the test opens them in the order it wants them to settle.
     */
    @Test
    fun `two toggles whose writes settle out of order still leave the server holding the final selection`() =
        threadTest {
            conversation() // mcp_servers: []
            val writes = OutOfOrderMcpWrites(conversationsApi)
            val viewModel = viewModel(conversations = writes)
            viewModel.load()
            viewModel.awaitLoaded()

            viewModel.toggleTool("sympy-math")
            drainMain() // the first write is out and parked on its gate, unsettled
            viewModel.toggleTool("websearch")
            drainMain() // whatever the second toggle was going to send, it has now been sent

            // Let the later write settle first and the earlier one afterwards —
            // exactly the reordering that left the server behind the sheet.
            // Serialised, the second write has not been sent yet, so releasing
            // its gate up front simply lets it through when its turn comes.
            writes.release(1)
            writes.release(0)
            writes.awaitSettled(2)

            val shown = viewModel.awaitLoaded().conversation.mcpServers
            assertEquals(listOf("sympy-math", "websearch"), shown)
            assertEquals("the server must end up holding what the sheet shows", shown, writes.stored)
        }

    @Test
    fun `toggleTool is refused outright while a run is active`() = threadTest {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        viewModel.awaitLoaded()
        viewModel.onComposerChange("go")
        transport.payloads = listOf(RUN_STARTED)
        transport.stayOpen = true
        viewModel.send()
        viewModel.awaitState { it.runActive }

        viewModel.toggleTool("sympy-math")

        // Only the load's own GET reached the server — send() goes through
        // the fake stream transport, so the guard means toggleTool never
        // even tries the PUT.
        assertEquals(1, server.requestCount)
    }

    private companion object {
        const val CONVERSATION_ID = "39dc7f47-91da-4a0f-b731-59f507a12c1b"
        const val RUN_STARTED = """{"type": "run_started", "run_id": "run-1"}"""
    }
}

/**
 * A [ConversationsRepository] whose `mcp_servers_json` writes settle only when
 * the test opens their gate, so completion order is chosen rather than raced.
 * [stored] is the server's copy: written when a call *settles*, which is the
 * whole point — the array that lands last is the one the server keeps.
 *
 * The write is [NonCancellable] deliberately. `ApiClient` runs a blocking
 * OkHttp call, so cancelling the coroutine around a PUT already on the wire
 * does not recall it — the server still applies it. A fake that let
 * cancellation abort the write would model a client this app does not have,
 * and would hide the race being exercised.
 */
private class OutOfOrderMcpWrites(api: ApiClient) : ConversationsRepository(api) {
    private val gates = List(GATE_COUNT) { CompletableDeferred<Unit>() }
    private val settled = Channel<Int>(Channel.UNLIMITED)
    private val nextIndex = AtomicInteger(0)

    @Volatile
    var stored: List<String> = emptyList()
        private set

    override suspend fun setMcpServers(id: String, serverIds: List<String>): Result<Unit> =
        withContext(NonCancellable) {
            val index = nextIndex.getAndIncrement()
            // Bounded on purpose. NonCancellable models "a request already on
            // the wire is not recalled by cancelling its coroutine" — which
            // also means `store.clear()` cannot kill this, so an unbounded
            // await on a gate the test never releases parks a coroutine on
            // Dispatchers.Main *forever*. The next class to call
            // `Dispatchers.setMain` then dies with "Main is used concurrently
            // with setting it", and the flake gets blamed on that class.
            // Reproduced at ~1 run in 5 across the full suite.
            runCatching { withTimeout(GATE_TIMEOUT_MS) { gates[index].await() } }
            stored = serverIds
            settled.send(index)
            Result.success(Unit)
        }

    /** Lets write [index] complete. Safe to call before that write has arrived. */
    fun release(index: Int) {
        gates[index].complete(Unit)
    }

    suspend fun awaitSettled(count: Int) {
        withTimeout(AWAIT_TIMEOUT_MS) { repeat(count) { settled.receive() } }
    }

    private companion object {
        const val GATE_COUNT = 8
        /** A deadlock guard, not a timing assumption — every await here is signalled, not slept on. */
        const val AWAIT_TIMEOUT_MS = 10_000L

        /**
         * Ceiling on a *non-cancellable* park, so it must be shorter than the
         * teardown's `awaitTermination` or a leaked write outlives the class.
         */
        const val GATE_TIMEOUT_MS = 2_000L
    }
}
