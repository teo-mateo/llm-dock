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
import com.hpz.llmdockchat.testing.FakeDraftStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.quiesceAndRelease
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

/**
 * Prompt selection by reference (F03 follow-up): the selection is the
 * conversation's `prompt_id`, not a content match. Selecting PUTs the id
 * alone (the server resolves the content); detaching PUTs an explicit
 * `prompt_id: null` with `main_system_prompt: ""`.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadPromptSelectionTest {

    private lateinit var server: MockWebServer
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
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "prompt-main") }

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
        // Inert on purpose, for the same reason as the other thread tests: a
        // live ladder read would consume a queued MockWebServer response and
        // shift every takeRequest() assertion.
        servicesRepository = ServicesRepository(ApiClient(client, FakeServerUrlStore(), ApiJson, Dispatchers.IO))
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

    private fun enqueue(body: String) = server.enqueue(MockResponse.Builder().body(body).build())

    private fun conversation(fixture: String = "conversation_multi_turn.json") =
        server.enqueue(MockResponse.Builder().body(readFixture(fixture)).build())

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

    private fun threadTest(body: suspend CoroutineScope.() -> Unit) = runBlocking { body() }

    private suspend fun openedThread(): ThreadViewModel =
        viewModel().also { it.load() }.also { it.awaitLoaded() }

    private suspend fun ThreadViewModel.awaitLoaded(): ThreadUiState.Loaded =
        withTimeout(10_000) { state.first { it is ThreadUiState.Loaded } as ThreadUiState.Loaded }

    private suspend fun ThreadViewModel.awaitState(
        predicate: (ThreadUiState.Loaded) -> Boolean,
    ): ThreadUiState.Loaded = withTimeout(10_000) {
        state.first { it is ThreadUiState.Loaded && predicate(it) } as ThreadUiState.Loaded
    }

    // -- selection ------------------------------------------------------------

    @Test
    fun `selecting a prompt updates the reference and PUTs the id alone`() = threadTest {
        conversation()
        enqueue("""{"id": "$CONVERSATION_ID"}""")
        val viewModel = openedThread()
        assertNull(viewModel.awaitLoaded().conversation.promptId)

        viewModel.selectPrompt("c2efe71a-cd7b")

        val state = viewModel.awaitState { it.conversation.promptId == "c2efe71a-cd7b" }
        assertEquals("c2efe71a-cd7b", state.conversation.promptId)
        server.takeRequest()
        assertEquals("""{"prompt_id":"c2efe71a-cd7b"}""", server.takeRequest().body?.utf8().orEmpty())
    }

    /**
     * The behaviour change the switch exists for: before it, a thread whose
     * stored text happened to equal a prompt's content was treated as
     * already on that prompt and the selection no-opped. The stored copy is
     * not the selection — the reference is — so the PUT still goes out.
     */
    @Test
    fun `a legacy conversation whose text matches a prompt's content is still unreferenced`() = threadTest {
        enqueue(
            """{"id":"$CONVERSATION_ID","title":"t","main_service":"llamacpp-gemma-4-26b-a4b-it-q8","messages":[],""" +
                """"mcp_servers":[],"active_run":null,""" +
                """"main_system_prompt":"You are a terse, careful assistant."}""",
        )
        enqueue("""{"id": "$CONVERSATION_ID"}""")
        val viewModel = openedThread()

        viewModel.selectPrompt("c2efe71a-cd7b")

        val state = viewModel.awaitState { it.conversation.promptId == "c2efe71a-cd7b" }
        assertEquals("You are a terse, careful assistant.", state.conversation.mainSystemPrompt)
        server.takeRequest()
        assertEquals("""{"prompt_id":"c2efe71a-cd7b"}""", server.takeRequest().body?.utf8().orEmpty())
    }

    // -- detach ----------------------------------------------------------------

    @Test
    fun `detaching clears the reference and sends the explicit null body`() = threadTest {
        conversation("conversation_with_prompt.json")
        enqueue("""{"id": "$CONVERSATION_ID"}""")
        val viewModel = openedThread()
        assertEquals("c2efe71a-cd7b", viewModel.awaitLoaded().conversation.promptId)

        viewModel.selectPrompt(null)

        val state = viewModel.awaitState { it.conversation.promptId == null }
        assertNull(state.conversation.promptId)
        server.takeRequest()
        assertEquals("""{"prompt_id":null,"main_system_prompt":""}""", server.takeRequest().body?.utf8().orEmpty())
    }

    // -- no-op and failure ------------------------------------------------------

    @Test
    fun `reselecting the current reference sends nothing`() = threadTest {
        conversation("conversation_with_prompt.json")
        val viewModel = openedThread()

        viewModel.selectPrompt("c2efe71a-cd7b")

        server.takeRequest()
        assertNull("no second request may be in flight", server.takeRequest(200, TimeUnit.MILLISECONDS))
    }

    @Test
    fun `a failed select reverts the reference and surfaces the server's error`() = threadTest {
        conversation()
        server.enqueue(
            MockResponse.Builder().code(404).body("""{"error": "Prompt not found"}""").build(),
        )
        val viewModel = openedThread()

        viewModel.selectPrompt("ghost-prompt")

        val state = viewModel.awaitState { it.actionError != null }
        assertNull(state.conversation.promptId)
        assertEquals("Prompt not found", state.actionError)
    }

    private companion object {
        const val CONVERSATION_ID = "39dc7f47-91da-4a0f-b731-59f507a12c1b"
    }
}
