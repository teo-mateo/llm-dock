package com.hpz.llmdockchat.feature.thread

import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelProvider
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
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.data.model.MessageRole
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.testing.FakeDraftStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.quiesceAndRelease
import com.hpz.llmdockchat.testing.readFixture
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import mockwebserver3.Dispatcher
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.QueueDispatcher
import mockwebserver3.RecordedRequest
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * A turn is built server-side from the stored conversation, so a send that
 * starts while a settings write is still on the wire runs with the tools,
 * prompt, model or reasoning level the user just moved off: the sheet showed the
 * new choice and the model never saw it. Send therefore waits for confirmation.
 *
 * Every write here is parked at the server rather than at a fake repository — one
 * `PUT /api/chat/conversations/<id>` per setting, answered only when the test
 * says so. The request path whose completion is being waited on is production
 * code, and the ordering is chosen rather than raced.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadSettingsWriteGateTest {

    private lateinit var server: MockWebServer
    private lateinit var gate: GatedSettingsWrites
    private lateinit var transport: FakeSseTransport
    private lateinit var drafts: FakeDraftStore
    private lateinit var repository: ChatRepository
    private lateinit var servicesStreamRepository: ServicesStreamRepository
    private lateinit var servicesRepository: ServicesRepository
    private lateinit var openRouterModelsRepository: OpenRouterModelsRepository
    private lateinit var conversationsRepository: ConversationsRepository
    private lateinit var mcpServersRepository: McpServersRepository
    private lateinit var promptsRepository: PromptsRepository
    private val store = ViewModelStore()
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "settings-main") }

    @Before
    fun setUp() {
        Dispatchers.setMain(mainExecutor.asCoroutineDispatcher())
        server = MockWebServer()
        gate = GatedSettingsWrites()
        server.dispatcher = gate
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
        // Inert on purpose: a live ladder read would consume a queued response and
        // move every assertion about what the server was asked for.
        servicesRepository = ServicesRepository(ApiClient(client, FakeServerUrlStore(), ApiJson, Dispatchers.IO))
        openRouterModelsRepository = OpenRouterModelsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        val api = ApiClient(client, urlStore, ApiJson, Dispatchers.IO)
        conversationsRepository = ConversationsRepository(api)
        mcpServersRepository = McpServersRepository(api)
        promptsRepository = PromptsRepository(api)
    }

    @After
    fun tearDown() {
        store.clear()
        // A test that threw mid-flight leaves a write parked; releasing lets the
        // server shut its queue down instead of timing out in teardown.
        listOf(TOOLS, PROMPT, REASONING, MODEL).forEach(gate::release)
        server.close()
        mainExecutor.quiesceAndRelease()
        Dispatchers.resetMain()
    }

    private fun conversation(fixture: String = "conversation_multi_turn.json") =
        gate.enqueue(MockResponse.Builder().body(readFixture(fixture)).build())

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
                )
            }
        },
    )[ThreadViewModel::class]

    private suspend fun CoroutineScope.openedThread(): Pair<ThreadViewModel, ThreadUiState.Loaded> {
        conversation()
        val viewModel = viewModel()
        viewModel.load()
        return viewModel to viewModel.awaitLoaded()
    }

    /**
     * The state while a settings write is unconfirmed: no Send, the draft left
     * where the user typed it, and no turn opened.
     */
    private suspend fun CoroutineScope.assertBlockedOnSend(
        viewModel: ThreadViewModel,
        draft: String,
    ) {
        drainMain()
        val pending = viewModel.awaitState { it.settingsPending }
        assertFalse("Send must not be offered while a settings write is unconfirmed", pending.canSend)
        viewModel.send()
        drainMain()
        assertTrue(
            "the turn must not start before the settings write is confirmed",
            transport.requests.isEmpty(),
        )
        assertEquals("the draft stays put", draft, viewModel.awaitLoaded().composer)
    }

    private suspend fun CoroutineScope.sendNowSettled(viewModel: ThreadViewModel) {
        transport.payloads = listOf(RUN_STARTED)
        transport.stayOpen = true
        viewModel.send()
        drainMain()
        viewModel.awaitState { it.runActive }
        assertEquals(1, transport.requests.size)
        assertTrue(transport.requests.first().path.endsWith("/messages"))
    }

    @Test
    fun `a tool write still on the wire blocks the send it was meant to affect`() = threadTest {
        val (viewModel, _) = openedThread()
        viewModel.onComposerChange("does the fetch tool work?")

        viewModel.toggleTool("webfetch")
        // Same main-thread turn as the toggle, before anything has been drained:
        // the write is counted as it is requested, not when its coroutine runs.
        viewModel.send()
        assertTrue("no turn may open on the toggle's own turn", transport.requests.isEmpty())
        assertBlockedOnSend(viewModel, "does the fetch tool work?")

        gate.release(TOOLS)
        assertTrue(viewModel.awaitState { !it.settingsPending }.canSend)
        sendNowSettled(viewModel)
    }

    @Test
    fun `a prompt write still on the wire blocks the send it was meant to affect`() = threadTest {
        val (viewModel, _) = openedThread()
        viewModel.onComposerChange("answer with the new prompt")

        viewModel.selectPrompt("p-1")
        assertBlockedOnSend(viewModel, "answer with the new prompt")

        gate.release(PROMPT)
        assertTrue(viewModel.awaitState { !it.settingsPending }.canSend)
        sendNowSettled(viewModel)
    }

    @Test
    fun `a reasoning-level write still on the wire blocks the send it was meant to affect`() = threadTest {
        val (viewModel, _) = openedThread()
        viewModel.onComposerChange("think about this")

        viewModel.selectReasoningLevel("low")
        assertBlockedOnSend(viewModel, "think about this")

        gate.release(REASONING)
        assertTrue(viewModel.awaitState { !it.settingsPending }.canSend)
        sendNowSettled(viewModel)
    }

    @Test
    fun `a model switch still on the wire blocks the send it was meant to affect`() = threadTest {
        val (viewModel, _) = openedThread()
        viewModel.onComposerChange("answer on the new model")

        viewModel.switchModel(ModelRef.Local("vllm-qwen3"))
        assertBlockedOnSend(viewModel, "answer on the new model")

        // The switch re-reads the conversation once the write settles, and that
        // reload must not report a settled state while the write is unconfirmed.
        conversation()
        gate.release(MODEL)
        assertTrue(viewModel.awaitState { !it.settingsPending }.canSend)
        sendNowSettled(viewModel)
    }

    /**
     * The gate must not cost anything when the write never confirms: a failed
     * write releases Send, and the draft it was blocking is still there to send.
     */
    @Test
    fun `a failed settings write releases Send and keeps the draft`() = threadTest {
        val (viewModel, _) = openedThread()
        viewModel.onComposerChange("does the fetch tool work?")
        gate.fail(TOOLS)

        viewModel.toggleTool("webfetch")
        drainMain()
        viewModel.awaitState { it.settingsPending }
        gate.release(TOOLS)

        val state = viewModel.awaitState { it.actionError != null }
        assertTrue("a failed write must not leave Send blocked", state.canSend)
        assertFalse(state.settingsPending)
        assertEquals("does the fetch tool work?", state.composer)
        assertTrue(transport.requests.isEmpty())
    }

    /**
     * A reload is not an escape hatch: the write is still unconfirmed, so the
     * rebuilt state carries the gate rather than clearing it.
     */
    @Test
    fun `a reload while a settings write is in flight keeps Send gated`() = threadTest {
        val (viewModel, _) = openedThread()
        viewModel.onComposerChange("hold on")
        viewModel.toggleTool("webfetch")
        drainMain()
        viewModel.awaitState { it.settingsPending }

        conversation("conversation_with_prompt.json")
        viewModel.load()

        val reloaded = viewModel.awaitState { it.conversation.promptId != null }
        assertTrue("a reload may not clear an unconfirmed write", reloaded.settingsPending)
        assertFalse(reloaded.canSend)
        gate.release(TOOLS)
    }

    @Test
    fun `edit-and-resend cannot be confirmed while a settings write is in flight`() = threadTest {
        val (viewModel, loaded) = openedThread()
        val target = loaded.thread.messages.first { it.role == MessageRole.USER }

        viewModel.beginEdit(target)
        viewModel.onComposerChange("edited while saving")
        viewModel.toggleTool("webfetch")
        drainMain()
        viewModel.awaitState { it.settingsPending }

        viewModel.requestEditConfirm()
        assertNull(
            "confirming an edit here would POST the turn past an unconfirmed write",
            viewModel.awaitLoaded().pendingEdit,
        )

        gate.release(TOOLS)
        viewModel.awaitState { !it.settingsPending }
        viewModel.requestEditConfirm()
        assertNotNull(viewModel.awaitLoaded().pendingEdit)
        assertTrue(transport.requests.isEmpty())
    }

    private fun threadTest(body: suspend CoroutineScope.() -> Unit) = runBlocking { body() }

    /**
     * Runs the main dispatcher's queue dry. [mainExecutor] is single-threaded and
     * FIFO, so "has the write gone out yet?" is a settled question rather than a
     * race — and the unconfirmed write is still unconfirmed afterwards, because
     * the server is the thing holding it.
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

    private companion object {
        const val CONVERSATION_ID = "39dc7f47-91da-4a0f-b731-59f507a12c1b"
        const val RUN_STARTED = """{"type": "run_started", "run_id": "run-1"}"""
    }
}

/**
 * Answers every conversation-settings `PUT` only when the test releases that
 * setting's gate, and delegates everything else to the ordinary response queue.
 *
 * The gate lives at the server rather than in a repository subclass so that the
 * write under test is the one the app really issues — a parked response is what
 * "not confirmed yet" means on this client. Releasing before a write arrives is
 * safe: the gate is simply already open when it does.
 */
private class GatedSettingsWrites : Dispatcher() {
    private val queue = QueueDispatcher()
    private val gates = ConcurrentHashMap<String, CompletableDeferred<Unit>>()

    @Volatile
    private var failedKind: String? = null

    fun enqueue(response: MockResponse) {
        queue.enqueue(response)
    }

    fun fail(kind: String) {
        failedKind = kind
    }

    fun release(kind: String) {
        gates.getOrPut(kind) { CompletableDeferred() }.complete(Unit)
    }

    override fun dispatch(request: RecordedRequest): MockResponse {
        val kind = request.settingsWriteKind() ?: return queue.dispatch(request)
        val gate = gates.getOrPut(kind) { CompletableDeferred() }
        runBlocking { withTimeout(GATE_TIMEOUT_MS) { gate.await() } }
        return if (failedKind == kind) {
            MockResponse.Builder().code(500).body("""{"error": "Conversation not found"}""").build()
        } else {
            MockResponse.Builder().body("""{"id": "$CONVERSATION_ID"}""").build()
        }
    }

    private companion object {
        const val CONVERSATION_ID = "39dc7f47-91da-4a0f-b731-59f507a12c1b"

        /**
         * A deadlock guard, not a timing assumption — every park here is released
         * by the test. Bounded because a leaked park outlives the class and the
         * next `Dispatchers.setMain` pays for it.
         */
        const val GATE_TIMEOUT_MS = 5_000L
    }
}

/** Which conversation setting a body is writing, by the field it names. */
private fun RecordedRequest.settingsWriteKind(): String? {
    if (method != "PUT") return null
    val body = body?.utf8() ?: return null
    return when {
        TOOLS_FIELD in body -> TOOLS
        PROMPT_FIELD in body -> PROMPT
        REASONING_FIELD in body -> REASONING
        MODEL_FIELD in body -> MODEL
        else -> null
    }
}

private const val TOOLS = "tools"
private const val PROMPT = "prompt"
private const val REASONING = "reasoning"
private const val MODEL = "model"
private const val TOOLS_FIELD = "mcp_servers_json"
private const val PROMPT_FIELD = "prompt_id"
private const val REASONING_FIELD = "reasoning_level"
private const val MODEL_FIELD = "main_service"
