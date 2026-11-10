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
import com.hpz.llmdockchat.data.ProviderModelsRepository
import com.hpz.llmdockchat.data.PromptsRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.data.model.displayName
import com.hpz.llmdockchat.data.model.wireValue
import com.hpz.llmdockchat.testing.NoOpConversationAttachments
import com.hpz.llmdockchat.testing.NoOpAutoSendClaims
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
 * F16 on the thread screen: a `<provider>:<model>` thread opens as itself, the
 * model switch lists each provider as its own group, and a provider ref never
 * gets a reasoning control.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ThreadProviderModelTest {

    private lateinit var server: MockWebServer
    private lateinit var transport: FakeSseTransport
    private lateinit var servicesTransport: FakeSseTransport
    private lateinit var drafts: FakeDraftStore
    private lateinit var repository: ChatRepository
    private lateinit var servicesStreamRepository: ServicesStreamRepository
    private lateinit var servicesRepository: ServicesRepository
    private lateinit var openRouterModelsRepository: OpenRouterModelsRepository
    private lateinit var providerModelsRepository: ProviderModelsRepository
    private lateinit var conversationsRepository: ConversationsRepository
    private lateinit var mcpServersRepository: McpServersRepository
    private lateinit var promptsRepository: PromptsRepository
    private val store = ViewModelStore()
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "provider-main") }

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
        providerModelsRepository = ProviderModelsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
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

    private fun enqueue(response: MockResponse) = server.enqueue(response)

    private fun conversation(mainService: String = PROVIDER_REF, lastRunError: String? = null) = enqueue(
        """{"id":"$CONVERSATION_ID","title":"t","main_service":"$mainService","messages":[],""" +
            """"mcp_servers":[],"active_run":null,"reasoning_level":null,""" +
            """"last_run":${lastRunError?.let { """{"id":"run-1","status":"failed","error":"$it"}""" } ?: "null"}}""",
    )

    private fun services(vararg rows: String) =
        enqueue("""{"services":[${rows.joinToString(",")}],"total":${rows.size}}""")

    private fun ladderRow(name: String, vararg ids: String) =
        """{"name":"$name","status":"running","kind":"chat","host_port":3301,"reasoning_levels":[""" +
            ids.joinToString(",") { """{"id":"$it","effort":"$it"}""" } + """]}"""

    private fun viewModel(): ThreadViewModel = ViewModelProvider.create(
        store,
        viewModelFactory {
            initializer {
                ThreadViewModel(
                    conversationId = CONVERSATION_ID,
                    repository = repository,
                    drafts = drafts,
                    conversationAttachments = NoOpConversationAttachments(),
                    autoSendClaims = NoOpAutoSendClaims(),
                    servicesStreamRepository = servicesStreamRepository,
                    servicesRepository = servicesRepository,
                    openRouterModelsRepository = openRouterModelsRepository,
                    providerModelsRepository = providerModelsRepository,
                    conversationsRepository = conversationsRepository,
                    mcpServersRepository = mcpServersRepository,
                    promptsRepository = promptsRepository,
                    coalesceWindowMs = 0,
                )
            }
        },
    )[ThreadViewModel::class]

    private fun threadTest(body: suspend CoroutineScope.() -> Unit) = runBlocking { body() }

    private suspend fun openedThread(): ThreadViewModel = viewModel().also { it.load() }.also { it.awaitLoaded() }

    private suspend fun ThreadViewModel.awaitLoaded(): ThreadUiState.Loaded =
        withTimeout(10_000) { state.first { it is ThreadUiState.Loaded } as ThreadUiState.Loaded }

    private suspend fun ThreadViewModel.awaitState(
        predicate: (ThreadUiState.Loaded) -> Boolean,
    ): ThreadUiState.Loaded = withTimeout(10_000) {
        state.first { it is ThreadUiState.Loaded && predicate(it) } as ThreadUiState.Loaded
    }

    private fun takeAll(): List<RecordedRequest> = List(server.requestCount) { server.takeRequest() }

    @Test
    fun `a thread on a provider model that is no longer listed opens as itself and shows the model id`() = threadTest {
        conversation()
        services(ladderRow("vllm-a", "off"))
        val viewModel = openedThread()

        val state = viewModel.awaitState { it.laddersByService.isNotEmpty() }

        assertEquals(ModelRef.Provider("mistral", "mistral-large-latest"), state.conversation.modelRef)
        assertEquals("mistral-large-latest", state.conversation.modelRef.displayName)
        assertEquals(PROVIDER_REF, state.conversation.modelRef.wireValue)
        val paths = takeAll().map { it.url.encodedPath }
        assertTrue(paths.none { it.contains("providers") })
    }

    @Test
    fun `the reasoning-level control is absent on a provider-model thread`() = threadTest {
        conversation()
        services(ladderRow("vllm-a", "off", "low", "xhigh"))
        val viewModel = openedThread()

        val state = viewModel.awaitState { it.laddersByService.containsKey("vllm-a") }

        assertEquals(emptyList<String>(), state.ladder)
        assertEquals(false, state.reasoningControlVisible)
    }

    @Test
    fun `the model switch offers one group per usable provider, in server order`() = threadTest {
        conversation("vllm-a")
        services(ladderRow("vllm-a", "off"))
        val viewModel = openedThread()

        enqueue("""{"configured":false,"current":[]}""")
        enqueue(readFixture("provider_models.json"))
        viewModel.openModelPicker()

        val picker = viewModel.awaitState { it.modelPicker?.providerGroups?.isNotEmpty() == true }.modelPicker!!

        assertEquals(listOf("Mistral"), picker.providerGroups.map { it.name })
        assertEquals(
            listOf("mistral:mistral-large-latest", "mistral:codestral-latest"),
            picker.providerGroups.single().models.map { it.ref.wireValue },
        )
    }

    @Test
    fun `a failing provider call leaves the local and OpenRouter options of the model switch intact`() = threadTest {
        conversation("vllm-a")
        services(ladderRow("vllm-a", "off"))
        val viewModel = openedThread()

        enqueue("""{"configured":true,"current":[{"id":"anthropic/claude-sonnet-5","label":"Sonnet"}]}""")
        enqueue(MockResponse.Builder().code(503).body("""{"error":"unavailable"}""").build())
        servicesTransport.payloads = listOf(
            """{"type":"snapshot","data":{"services":[{"name":"vllm-a","status":"running","kind":"chat","host_port":3301}]}}""",
        )
        viewModel.openModelPicker()

        val picker = viewModel.awaitState {
            it.modelPicker?.services?.isNotEmpty() == true && it.modelPicker?.remoteModels?.isNotEmpty() == true
        }.modelPicker!!

        assertEquals(listOf("vllm-a"), picker.services.map { it.name })
        assertEquals(listOf("anthropic/claude-sonnet-5"), picker.remoteModels.map { it.modelId })
        assertTrue(picker.remoteModelsConfigured)
        assertTrue(picker.providerGroups.isEmpty())
    }

    @Test
    fun `switching to a provider model sends its provider-prefixed id as main_service`() = threadTest {
        conversation("vllm-a")
        services(ladderRow("vllm-a", "off"))
        val viewModel = openedThread()
        viewModel.awaitState { it.laddersByService.isNotEmpty() }

        enqueue("""{"id":"$CONVERSATION_ID"}""")
        conversation("mistral:codestral-latest")
        viewModel.switchModel(ModelRef.Provider("mistral", "codestral-latest"))

        val switched = viewModel.awaitState { it.conversation.modelRef is ModelRef.Provider }
        assertEquals(ModelRef.Provider("mistral", "codestral-latest"), switched.conversation.modelRef)
        val put = takeAll().single { it.method == "PUT" }
        assertEquals("""{"main_service":"mistral:codestral-latest"}""", put.body?.utf8())
    }

    @Test
    fun `a turn on an unconfigured provider surfaces the server's error frame`() = threadTest {
        conversation()
        services()
        transport.payloads = listOf(RUN_STARTED, """{"error": "$NOT_CONFIGURED"}""")
        conversation(lastRunError = NOT_CONFIGURED)
        val viewModel = openedThread()
        viewModel.onComposerChange("hello")
        viewModel.send()

        val state = viewModel.awaitState { it.thread.streaming == null && it.runError != null }

        assertEquals(NOT_CONFIGURED, state.runError)
        assertEquals(ModelRef.Provider("mistral", "mistral-large-latest"), state.conversation.modelRef)
        assertEquals(false, state.runActive)
    }

    private companion object {
        const val CONVERSATION_ID = "c-provider"
        const val PROVIDER_REF = "mistral:mistral-large-latest"
        const val RUN_STARTED = """{"type": "run_started", "run_id": "run-1"}"""
        const val NOT_CONFIGURED = "Provider 'mistral' is not configured. Add its API key in Settings."
    }
}
