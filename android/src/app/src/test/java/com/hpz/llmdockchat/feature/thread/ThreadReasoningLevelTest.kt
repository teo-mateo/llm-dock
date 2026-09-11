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
import com.hpz.llmdockchat.data.PromptsRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.testing.FakeDraftStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.quiesceAndRelease
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * F15 on the thread screen's state machine: where the ladder comes from, what
 * happens to it when the model changes, and what a level write does to the
 * conversation.
 *
 * Unlike every other `Thread*Test`, this one's [ServicesRepository] is live —
 * the ladder is the subject here, so the `GET /api/services` it issues is part
 * of the choreography rather than interference. Two consequences, both handled
 * below: every test enqueues its responses in the order the screen makes them
 * (thread, then services), and a test that asserts on a PUT body reads requests
 * in that same order.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadReasoningLevelTest {

    private lateinit var server: MockWebServer
    private lateinit var transport: FakeSseTransport
    private lateinit var servicesTransport: FakeSseTransport
    private lateinit var drafts: FakeDraftStore
    private lateinit var repository: ChatRepository
    private lateinit var servicesStreamRepository: ServicesStreamRepository
    private lateinit var servicesRepository: ServicesRepository
    private lateinit var openRouterModelsRepository: OpenRouterModelsRepository
    private lateinit var conversationsRepository: ConversationsRepository
    private lateinit var mcpServersRepository: McpServersRepository
    private lateinit var promptsRepository: PromptsRepository
    private val store = ViewModelStore()
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "level-main") }

    @Before
    fun setUp() {
        Dispatchers.setMain(mainExecutor.asCoroutineDispatcher())
        server = MockWebServer()
        server.start()
        transport = FakeSseTransport()
        servicesTransport = FakeSseTransport()
        drafts = FakeDraftStore()
        val urlStore = FakeServerUrlStore(baseUrl(server.url("/").toString()))
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .authenticator(SessionAuthenticator(FakeTokenStore("totp-test"), SessionState(), Reauthenticator.NoCredential))
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
        repository = ChatRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO), transport)
        servicesStreamRepository = ServicesStreamRepository(servicesTransport)
        servicesRepository = ServicesRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        openRouterModelsRepository = OpenRouterModelsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        conversationsRepository = ConversationsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
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

    // -- payloads -------------------------------------------------------------

    private fun enqueue(body: String) = server.enqueue(MockResponse.Builder().body(body).build())

    private fun enqueue(response: MockResponse) = server.enqueue(response)

    private fun conversation(
        mainService: String = "vllm-a",
        reasoningLevel: String? = null,
    ) = enqueue(
        """{"id":"$CONVERSATION_ID","title":"t","main_service":"$mainService","messages":[],""" +
            """"mcp_servers":[],"active_run":null,""" +
            """"reasoning_level":${reasoningLevel?.let { "\"$it\"" } ?: "null"}}""",
    )

    private fun ladderRow(name: String, vararg ids: String) =
        """{"name":"$name","status":"running","kind":"chat","host_port":3301,"reasoning_levels":[""" +
            ids.joinToString(",") { """{"id":"$it","effort":"$it"}""" } + """],"api_key":"llmd-secret"}"""

    private fun noLadderRow(name: String) =
        """{"name":"$name","status":"running","kind":"chat","host_port":3302,"api_key":"llmd-secret"}"""

    private fun services(vararg rows: String) =
        enqueue("""{"services":[${rows.joinToString(",")}],"total":${rows.size}}""")

    private fun viewModel(): ThreadViewModel = ViewModelProvider.create(
        store,
        viewModelFactory {
            initializer {
                ThreadViewModel(
                    conversationId = CONVERSATION_ID,
                    repository = repository,
                    drafts = drafts,
                    servicesStreamRepository = servicesStreamRepository,
                    servicesRepository = servicesRepository,
                    openRouterModelsRepository = openRouterModelsRepository,
                    conversationsRepository = conversationsRepository,
                    mcpServersRepository = mcpServersRepository,
                    promptsRepository = promptsRepository,
                    coalesceWindowMs = 0,
                    titleSettleDelayMs = 1,
                )
            }
        },
    )[ThreadViewModel::class]

    private fun threadTest(body: suspend CoroutineScope.() -> Unit) = runBlocking { body() }

    /** The screen's own entry: `ThreadScreen` calls `load()` on composition, so tests do too. */
    private suspend fun openedThread(): ThreadViewModel = viewModel().also { it.load() }.also { it.awaitLoaded() }

    private suspend fun ThreadViewModel.awaitLoaded(): ThreadUiState.Loaded =
        withTimeout(10_000) { state.first { it is ThreadUiState.Loaded } as ThreadUiState.Loaded }

    private suspend fun ThreadViewModel.awaitState(
        predicate: (ThreadUiState.Loaded) -> Boolean,
    ): ThreadUiState.Loaded = withTimeout(10_000) {
        state.first { it is ThreadUiState.Loaded && predicate(it) } as ThreadUiState.Loaded
    }

    private fun RecordedRequest.body(): String = this.body?.utf8().orEmpty()

    // -- F15-R1/R5 · where the ladder comes from --------------------------------

    @Test
    fun `the ladder for the thread's service arrives with the service snapshot`() = threadTest {
        conversation()
        services(ladderRow("vllm-a", "off", "low", "xhigh"), noLadderRow("vllm-b"))
        val viewModel = openedThread()

        // The ladder arrives on its own request, after the thread is on screen.
        val state = viewModel.awaitState { it.ladder.isNotEmpty() }

        assertEquals(listOf("off", "low", "xhigh"), state.ladder)
        assertTrue(state.reasoningControlVisible)
        assertEquals(false, state.reasoningStale)
    }

    /**
     * F15-R1's fourth criterion, and the reason the state holds a map rather
     * than one list: `switchModel` refetches the conversation and nothing else,
     * so a ladder copied at load would still describe the service just left —
     * offering a level the new model would reject.
     */
    @Test
    fun `switching models re-resolves the ladder with no second services fetch`() = threadTest {
        conversation("vllm-a")
        services(ladderRow("vllm-a", "off", "low"), noLadderRow("vllm-b"))
        val viewModel = openedThread()
        viewModel.awaitState { it.ladder.isNotEmpty() }
        // Both load requests have landed now: the thread, then the ladder.
        val afterLoad = server.requestCount

        enqueue("""{"id": "$CONVERSATION_ID"}""")
        conversation("vllm-b")
        viewModel.switchModel(ModelRef.Local("vllm-b"))

        val state = viewModel.awaitState { it.conversation.modelRef == ModelRef.Local("vllm-b") }
        assertEquals(emptyList<String>(), state.ladder)
        // The switch itself: one PUT + one thread reload, and no new GET /api/services.
        assertEquals(afterLoad + 2, server.requestCount)

        // And back again, still without a fetch — the choice survives a round trip.
        enqueue("""{"id": "$CONVERSATION_ID"}""")
        conversation("vllm-a")
        viewModel.switchModel(ModelRef.Local("vllm-a"))
        val back = viewModel.awaitState { it.ladder.isNotEmpty() }
        assertEquals(listOf("off", "low"), back.ladder)
        assertEquals(afterLoad + 4, server.requestCount)
    }

    /** F15-R8: an OpenRouter thread resolves no ladder and shows no control. */
    @Test
    fun `an openrouter thread shows no control even when the snapshot is full of ladders`() = threadTest {
        conversation("openrouter:anthropic/claude-sonnet-5")
        services(ladderRow("vllm-a", "off", "low"))
        val viewModel = openedThread()

        val state = viewModel.state.value as ThreadUiState.Loaded

        assertEquals(emptyList<String>(), state.ladder)
        assertEquals(false, state.reasoningControlVisible)
    }

    /** F15-R5: a ladder delta on the picker's live stream reaches the thread. */
    @Test
    fun `a ladder delta reaches the thread while the picker stream is live`() = threadTest {
        conversation()
        services(ladderRow("vllm-a", "off"))
        enqueue("""{"models":[],"configured":false}""")
        val viewModel = openedThread()

        servicesTransport.payloads = listOf(
            """{"type": "snapshot", "data": {"services": [{"name": "vllm-a", "status": "running",""" +
                """"kind": "chat", "host_port": 3301, "reasoning_levels": [{"id": "off"}, {"id": "xhigh"}]}]}}""",
        )
        viewModel.openModelPicker()

        val state = viewModel.awaitState { it.ladder == listOf("off", "xhigh") }
        assertEquals(listOf("off", "xhigh"), state.ladder)
    }

    /**
     * A failed ladder read keeps the ladder already on screen. Clearing it would
     * hide the chip — and the chip is the only way back to the sheet, so a
     * transient failure would make the control unrecoverable without leaving.
     */
    @Test
    fun `a failed ladder refresh leaves the known ladder alone`() = threadTest {
        conversation()
        services(ladderRow("vllm-a", "off", "low"))
        val viewModel = openedThread()
        viewModel.awaitState { it.ladder.isNotEmpty() }

        enqueue(MockResponse.Builder().code(500).body("boom").build())
        viewModel.openReasoningPicker()
        assertNotNull(server.takeRequest())
        server.takeRequest()
        server.takeRequest()

        assertEquals(listOf("off", "low"), viewModel.state.value.let { (it as ThreadUiState.Loaded).ladder })
        assertNotNull(viewModel.state.value.let { (it as ThreadUiState.Loaded).reasoningPicker })
    }

    // -- F15-R2/R4/R7 · choosing a level ---------------------------------------

    @Test
    fun `choosing a level writes it, updates the chip at once, and closes the sheet on success`() = threadTest {
        conversation()
        services(ladderRow("vllm-a", "off", "low"))
        enqueue("""{"id": "$CONVERSATION_ID"}""")
        val viewModel = openedThread()

        viewModel.selectReasoningLevel("low")

        val state = viewModel.awaitState { it.reasoningPicker == null && it.conversation.reasoningLevel == "low" }
        assertNull(state.reasoningPicker)
        // GET thread, GET services, PUT level — in that order.
        server.takeRequest()
        server.takeRequest()
        assertEquals("""{"reasoning_level":"low"}""", server.takeRequest().body())
    }

    /** F15-R4: clearing is the one write where the body's *null* is the payload. */
    @Test
    fun `choosing model default writes an explicit null and the chip reads default`() = threadTest {
        conversation(reasoningLevel = "low")
        services(ladderRow("vllm-a", "off", "low"))
        enqueue("""{"id": "$CONVERSATION_ID"}""")
        val viewModel = openedThread()
        assertEquals("low", viewModel.awaitLoaded().conversation.reasoningLevel)

        viewModel.selectReasoningLevel(null)

        viewModel.awaitState { it.conversation.reasoningLevel == null }
        server.takeRequest()
        server.takeRequest()
        assertEquals("""{"reasoning_level":null}""", server.takeRequest().body())
    }

    @Test
    fun `a failed write reverts to the server's value and surfaces the error`() = threadTest {
        conversation()
        services(ladderRow("vllm-a", "off", "low"))
        enqueue(
            MockResponse.Builder().code(400)
                .body("""{"error":"reasoning_level 'low' is not offered","code":"invalid_reasoning_level"}""")
                .build(),
        )
        val viewModel = openedThread()

        viewModel.selectReasoningLevel("low")

        val state = viewModel.awaitState { it.actionError != null }
        assertNull(state.conversation.reasoningLevel)
        // F15-R2: the sheet stays open on failure, no longer pending, so the
        // user sees the revert and can pick again.
        assertNotNull(state.reasoningPicker)
        assertEquals(false, state.reasoningPicker?.writePending)
    }

    /** F15-R7: a stale write's failure must not fight the newer choice. */
    @Test
    fun `a superseded write's failure leaves the newest choice alone`() = threadTest {
        conversation()
        services(ladderRow("vllm-a", "off", "low", "xhigh"))
        // Oldest write loses (the ladder moved under it), newest wins.
        enqueue(
            MockResponse.Builder().code(400)
                .body("""{"error":"reasoning_level 'low' is not offered","code":"invalid_reasoning_level"}""")
                .build(),
        )
        enqueue("""{"id": "$CONVERSATION_ID"}""")
        val viewModel = openedThread()

        viewModel.selectReasoningLevel("low")
        viewModel.selectReasoningLevel("xhigh")

        val state = viewModel.awaitState { it.reasoningPicker == null }
        assertEquals("xhigh", state.conversation.reasoningLevel)
        assertNull(state.actionError)
    }

    /** F15-R7's third criterion, mirroring `toggleTool`'s guard. */
    @Test
    fun `choosing a level during a run is refused outright and sends nothing`() = threadTest {
        conversation()
        services(ladderRow("vllm-a", "off", "low"))
        transport.payloads = listOf("""{"type": "run_started", "run_id": "run-1"}""")
        transport.stayOpen = true
        val viewModel = openedThread()
        viewModel.onComposerChange("hi")
        viewModel.send()
        val running = viewModel.awaitState { it.runActive }
        val requests = server.requestCount

        viewModel.selectReasoningLevel("low")
        viewModel.openReasoningPicker()

        assertEquals(running.conversation.reasoningLevel, viewModel.state.value.let { (it as ThreadUiState.Loaded).conversation.reasoningLevel })
        assertNull((viewModel.state.value as ThreadUiState.Loaded).reasoningPicker)
        assertEquals(requests, server.requestCount)
    }

    // -- F15-R6 · the dropped-level note ---------------------------------------

    @Test
    fun `the server's dropped-level note reaches the screen state above the composer`() = threadTest {
        conversation(reasoningLevel = "xhigh")
        services(ladderRow("vllm-a", "off", "low"))
        transport.payloads = listOf(
            """{"type": "run_started", "run_id": "run-1", "reasoning_level": null,""" +
                """ "reasoning_level_note": "Reasoning level 'xhigh' is not offered by this model and was ignored"}""",
        )
        transport.stayOpen = true
        val viewModel = openedThread()
        viewModel.onComposerChange("think about it")
        viewModel.send()

        val state = viewModel.awaitState { it.reasoningNotice != null }
        assertEquals("Reasoning level 'xhigh' is not offered by this model and was ignored", state.reasoningNotice)
    }

    /**
     * The plain frame — what a reattaching client always gets — leaves the note
     * absent rather than empty, so the notice row is not composed. F15 accepts
     * losing the note across a reconnect; the stale chip is the durable half.
     */
    @Test
    fun `a plain run_started carries no note`() = threadTest {
        conversation()
        services(ladderRow("vllm-a", "off", "low"))
        transport.payloads = listOf("""{"type": "run_started", "run_id": "run-1"}""")
        transport.stayOpen = true
        val viewModel = openedThread()
        viewModel.onComposerChange("hi")
        viewModel.send()

        val state = viewModel.awaitState { it.thread.streaming?.runId == "run-1" }
        assertNull(state.reasoningNotice)
    }

    private companion object {
        const val CONVERSATION_ID = "39dc7f47-91da-4a0f-b731-59f507a12c1b"
    }
}
