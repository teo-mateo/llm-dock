package com.hpz.llmdockchat.feature.newchat

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.PromptsRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.data.model.ModelOption
import com.hpz.llmdockchat.testing.FakeNewChatPreferences
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.MainDispatcherRule
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

/**
 * F03: the sheet's data load (F03-R1's third/fourth criteria, F03-R2, F03-R3)
 * and the create flow (F03-R1's fifth criterion). [ConversationsRepositoryTest]
 * covers the exact wire payloads; this covers the ViewModel's decisions on
 * top of them.
 */
class NewChatViewModelTest {

    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    private lateinit var server: MockWebServer
    private lateinit var conversationsRepository: ConversationsRepository
    private lateinit var servicesRepository: ServicesRepository
    private lateinit var promptsRepository: PromptsRepository
    private lateinit var mcpServersRepository: McpServersRepository
    private lateinit var openRouterModelsRepository: OpenRouterModelsRepository
    private lateinit var servicesStreamRepository: ServicesStreamRepository
    private lateinit var servicesStreamTransport: FakeSseTransport
    private lateinit var preferences: FakeNewChatPreferences

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        val urlStore = FakeServerUrlStore(
            (BaseUrl.normalize(server.url("/").toString()) as BaseUrlResult.Valid).baseUrl,
        )
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .build()
        val api = ApiClient(client, urlStore, ApiJson, Dispatchers.IO)
        conversationsRepository = ConversationsRepository(api)
        servicesRepository = ServicesRepository(api)
        promptsRepository = PromptsRepository(api)
        mcpServersRepository = McpServersRepository(api)
        openRouterModelsRepository = OpenRouterModelsRepository(api)
        // No payloads by default: most tests never open a picker, and an
        // empty FakeSseTransport just never emits rather than erroring.
        servicesStreamTransport = FakeSseTransport()
        servicesStreamRepository = ServicesStreamRepository(servicesStreamTransport)
        preferences = FakeNewChatPreferences()
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun viewModel() = NewChatViewModel(
        servicesRepository = servicesRepository,
        promptsRepository = promptsRepository,
        mcpServersRepository = mcpServersRepository,
        openRouterModelsRepository = openRouterModelsRepository,
        conversationsRepository = conversationsRepository,
        preferences = preferences,
        servicesStreamRepository = servicesStreamRepository,
    )

    /** Load order in [NewChatViewModel.load]: services, openrouter, prompts, mcp-servers. */
    private fun enqueueLoadResponses(
        services: String = readFixture("services_list.json"),
        openRouter: String = readFixture("openrouter_models.json"),
        prompts: String = readFixture("prompts.json"),
        mcpServers: String = readFixture("mcp_servers.json"),
    ) {
        server.enqueue(MockResponse.Builder().body(services).build())
        server.enqueue(MockResponse.Builder().body(openRouter).build())
        server.enqueue(MockResponse.Builder().body(prompts).build())
        server.enqueue(MockResponse.Builder().body(mcpServers).build())
    }

    private fun settled(viewModel: NewChatViewModel): NewChatUiState = runBlocking {
        withTimeout(10_000) {
            viewModel.state.first { it !is NewChatUiState.Loading }
        }
    }

    @Test
    fun `local services are filtered to chat-capable engines, excluding open-webui and embeddings`() {
        enqueueLoadResponses()
        val viewModel = viewModel()

        viewModel.load()
        val state = settled(viewModel) as NewChatUiState.Loaded

        val names = state.localServices.map { it.serviceName }
        assertFalse(names.contains("open-webui"))
        assertFalse(names.contains("vllm-bge-m3"))
        assertFalse(names.contains("vllm-nomic-embed-text-v1.5"))
        assertTrue(names.contains("llamacpp-gemma-4-26b-a4b-it-q8"))
        assertTrue(names.contains("vllm-qwen3-6-27b-fp8"))
    }

    @Test
    fun `prompts load ordered by sort_order and mcp servers load from the registry`() {
        enqueueLoadResponses()
        val viewModel = viewModel()

        viewModel.load()
        val state = settled(viewModel) as NewChatUiState.Loaded

        assertEquals(listOf("Agentic Project Work", "Terse Expert Oracle", "Thinking Partner"), state.prompts.map { it.name })
        assertTrue(state.mcpServers.any { it.id == "sympy-math" })
        assertEquals(null, state.selectedPromptId) // Default, every time the sheet opens
    }

    /**
     * F03-R2's fourth criterion: "the row shows only Default and does not
     * appear broken." [NewChatScreen] always renders the system-prompt row
     * off [NewChatUiState.Loaded.prompts] with no special-casing — an empty
     * list naturally leaves only the always-present "Default" choice in the
     * picker. What this test proves is the state side of that: an empty
     * `prompts` array from the server produces an empty (not null, not a
     * crash) list.
     */
    @Test
    fun `no managed prompts on the server leaves the prompts list empty, not broken`() {
        enqueueLoadResponses(prompts = """{"prompts": []}""")
        val viewModel = viewModel()

        viewModel.load()
        val state = settled(viewModel) as NewChatUiState.Loaded

        assertTrue(state.prompts.isEmpty())
        assertEquals(null, state.selectedPromptId)
    }

    /**
     * F03-R3's third criterion: "the row is hidden rather than empty."
     * [NewChatScreen] gates the whole Tools row on `mcpServers.isNotEmpty()`
     * — this proves the state that gate reads is correctly empty, not null
     * or a parse failure, when the registry has nothing enabled.
     */
    @Test
    fun `no mcp servers available leaves the row's backing list empty`() {
        enqueueLoadResponses(mcpServers = """{"servers": []}""")
        val viewModel = viewModel()

        viewModel.load()
        val state = settled(viewModel) as NewChatUiState.Loaded

        assertTrue(state.mcpServers.isEmpty())
        assertTrue(state.selectedMcpServerIds.isEmpty())
    }

    @Test
    fun `a remembered running local model is preselected with no warning`() {
        preferences = FakeNewChatPreferences(initialModel = "llamacpp-gemma-4-26b-a4b-it-q8")
        enqueueLoadResponses()
        val viewModel = viewModel()

        viewModel.load()
        val state = settled(viewModel) as NewChatUiState.Loaded

        val selected = state.selectedModel as ModelOption.LocalService
        assertEquals("llamacpp-gemma-4-26b-a4b-it-q8", selected.serviceName)
        assertFalse(state.rememberedModelUnavailable)
    }

    @Test
    fun `a remembered local model that stopped running requires an explicit choice`() {
        // vllm-qwen3-6-27b-fp8 is "exited" in the services fixture.
        preferences = FakeNewChatPreferences(initialModel = "vllm-qwen3-6-27b-fp8")
        enqueueLoadResponses()
        val viewModel = viewModel()

        viewModel.load()
        val state = settled(viewModel) as NewChatUiState.Loaded

        assertNull(state.selectedModel)
        assertTrue(state.rememberedModelUnavailable)
        assertFalse(state.canStart)
    }

    @Test
    fun `a remembered local model that no longer exists is treated as unavailable, not a crash`() {
        preferences = FakeNewChatPreferences(initialModel = "llamacpp-deleted-service")
        enqueueLoadResponses()
        val viewModel = viewModel()

        viewModel.load()
        val state = settled(viewModel) as NewChatUiState.Loaded

        assertNull(state.selectedModel)
        assertTrue(state.rememberedModelUnavailable)
    }

    @Test
    fun `a remembered OpenRouter model is preselected even if dropped from the curated list`() {
        preferences = FakeNewChatPreferences(initialModel = "openrouter:someone/retired-model")
        enqueueLoadResponses()
        val viewModel = viewModel()

        viewModel.load()
        val state = settled(viewModel) as NewChatUiState.Loaded

        val selected = state.selectedModel as ModelOption.Remote
        assertEquals("someone/retired-model", selected.modelId)
        assertFalse(state.rememberedModelUnavailable)
    }

    @Test
    fun `no remembered model at all leaves the sheet requiring an explicit choice`() {
        enqueueLoadResponses()
        val viewModel = viewModel()

        viewModel.load()
        val state = settled(viewModel) as NewChatUiState.Loaded

        assertNull(state.selectedModel)
        assertFalse(state.rememberedModelUnavailable) // nothing was remembered — not "unavailable"
        assertFalse(state.canStart)
    }

    /**
     * F07-R1's third criterion: a container started or stopped elsewhere
     * reaches an open picker with no manual refresh. `MainDispatcherRule`
     * runs `viewModelScope` unconfined, so the stream's snapshot and delta
     * are queued before [NewChatViewModel.load] runs — under Unconfined
     * dispatch both land, in order, before [settled] ever gets to observe an
     * intermediate state.
     */
    @Test
    fun `a services-stream delta updates the picker's live list with no manual refresh`() {
        enqueueLoadResponses()
        servicesStreamTransport.payloads = listOf(
            """{"type":"snapshot","data":{"services":[
                {"name":"llamacpp-gemma-4-31b-it-q8","status":"exited","kind":"chat","host_port":3303,"favorite":false}
            ],"total":1,"running":0,"stopped":1}}""",
            """{"type":"delta","service_name":"llamacpp-gemma-4-31b-it-q8","status":"running"}""",
        )
        val viewModel = viewModel()

        viewModel.load()
        // Not `settled()`: that only waits for the *first* non-Loading value,
        // and — since `.value` updates from the load and from the stream both
        // land before this collector is ever dispatched — could observe
        // either. Wait for the specific outcome instead.
        val state = runBlocking {
            withTimeout(10_000) {
                viewModel.state.first {
                    it is NewChatUiState.Loaded &&
                        it.services.any { s -> s.name == "llamacpp-gemma-4-31b-it-q8" && s.status == "running" }
                }
            }
        } as NewChatUiState.Loaded

        val service = state.services.first { it.name == "llamacpp-gemma-4-31b-it-q8" }
        assertEquals("running", service.status)
    }

    @Test
    fun `a failing services fetch is the failed state, the essential source for F03-R1`() {
        server.enqueue(MockResponse.Builder().code(503).body("""{"error": "Docker socket unavailable"}""").build())
        val viewModel = viewModel()

        viewModel.load()
        val state = settled(viewModel)

        assertTrue(state is NewChatUiState.Failed)
        assertEquals("Docker socket unavailable", (state as NewChatUiState.Failed).message)
    }

    @Test
    fun `create remembers the chosen model and tool selection, then opens the new thread`() {
        enqueueLoadResponses()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = settled(viewModel) as NewChatUiState.Loaded
        val model = loaded.localServices.first { it.serviceName == "llamacpp-gemma-4-26b-a4b-it-q8" }

        viewModel.selectModel(model)
        viewModel.toggleMcpServer("sympy-math")

        server.enqueue(MockResponse.Builder().body("""{"id": "new-conv-1"}""").build())
        server.enqueue(MockResponse.Builder().body("""{"id": "new-conv-1"}""").build()) // setMcpServers PUT

        var createdId: String? = null
        viewModel.create { createdId = it }

        val finalState = runBlocking {
            withTimeout(10_000) {
                viewModel.state.first { (it as? NewChatUiState.Loaded)?.creating == false && createdId != null }
            }
        }
        assertFalse((finalState as NewChatUiState.Loaded).creating)
        assertEquals("new-conv-1", createdId)
        assertEquals("llamacpp-gemma-4-26b-a4b-it-q8", preferences.rememberedModel)
        assertEquals(listOf("sympy-math"), preferences.rememberedMcpServerIds)
    }

    @Test
    fun `a failed create keeps the sheet open with the selection intact and shows the server's message`() {
        enqueueLoadResponses()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = settled(viewModel) as NewChatUiState.Loaded
        val model = loaded.localServices.first { it.serviceName == "llamacpp-gemma-4-26b-a4b-it-q8" }
        viewModel.selectModel(model)

        server.enqueue(MockResponse.Builder().code(400).body("""{"error": "main_service is required"}""").build())

        var created = false
        viewModel.create { created = true }

        val finalState = runBlocking {
            withTimeout(10_000) {
                viewModel.state.first { (it as? NewChatUiState.Loaded)?.createError != null }
            }
        }
        assertFalse(created)
        val loadedFinal = finalState as NewChatUiState.Loaded
        assertEquals("main_service is required", loadedFinal.createError)
        assertEquals(model, loadedFinal.selectedModel)
        assertFalse(loadedFinal.creating)
    }

    // -- S1 fix-up: the conversation is created but the tools PUT fails --

    @Test
    fun `when the conversation is created but setMcpServers fails, the sheet surfaces it instead of opening the thread`() {
        enqueueLoadResponses()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = settled(viewModel) as NewChatUiState.Loaded
        val model = loaded.localServices.first { it.serviceName == "llamacpp-gemma-4-26b-a4b-it-q8" }
        viewModel.selectModel(model)
        viewModel.toggleMcpServer("sympy-math")

        server.enqueue(MockResponse.Builder().body("""{"id": "new-conv-2"}""").build())
        server.enqueue(MockResponse.Builder().code(401).body("""{"error": "Sign in again to continue."}""").build())

        var createdId: String? = null
        viewModel.create { createdId = it }

        val finalState = runBlocking {
            withTimeout(10_000) {
                viewModel.state.first { (it as? NewChatUiState.Loaded)?.toolsFailure != null }
            }
        }
        val loadedFinal = finalState as NewChatUiState.Loaded
        // The conversation was NOT opened — the failure blocks navigation, not the create.
        assertNull(createdId)
        assertFalse(loadedFinal.creating)
        assertEquals("new-conv-2", loadedFinal.toolsFailure?.conversationId)
        assertEquals("Sign in again to continue.", loadedFinal.toolsFailure?.message)
        // Selections survive the failure, same as a failed create (F00-R4's "never swallow").
        assertEquals(model, loadedFinal.selectedModel)
        assertEquals(setOf("sympy-math"), loadedFinal.selectedMcpServerIds)
        assertFalse(loadedFinal.canStart) // Start is not the way out of this state
    }

    @Test
    fun `retryTools re-issues only the PUT and opens the thread on success`() {
        enqueueLoadResponses()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = settled(viewModel) as NewChatUiState.Loaded
        val model = loaded.localServices.first { it.serviceName == "llamacpp-gemma-4-26b-a4b-it-q8" }
        viewModel.selectModel(model)
        viewModel.toggleMcpServer("sympy-math")

        server.enqueue(MockResponse.Builder().body("""{"id": "new-conv-3"}""").build())
        server.enqueue(MockResponse.Builder().code(500).body("""{"error": "temporary failure"}""").build())
        viewModel.create {}
        runBlocking {
            withTimeout(10_000) { viewModel.state.first { (it as? NewChatUiState.Loaded)?.toolsFailure != null } }
        }

        // create() was NOT called again — only setMcpServers — so a single response is enough.
        server.enqueue(MockResponse.Builder().body("""{"id": "new-conv-3"}""").build())
        var createdId: String? = null
        viewModel.retryTools { createdId = it }

        val finalState = runBlocking {
            withTimeout(10_000) { viewModel.state.first { createdId != null } }
        }
        assertEquals("new-conv-3", createdId)
        assertNull((finalState as NewChatUiState.Loaded).toolsFailure)
        // 4 load GETs + POST create + failed PUT + retried PUT — never a second POST create.
        assertEquals(7, server.requestCount)
    }

    @Test
    fun `openAnyway opens the thread without retrying the failed PUT`() {
        enqueueLoadResponses()
        val viewModel = viewModel()
        viewModel.load()
        val loaded = settled(viewModel) as NewChatUiState.Loaded
        val model = loaded.localServices.first { it.serviceName == "llamacpp-gemma-4-26b-a4b-it-q8" }
        viewModel.selectModel(model)
        viewModel.toggleMcpServer("sympy-math")

        server.enqueue(MockResponse.Builder().body("""{"id": "new-conv-4"}""").build())
        server.enqueue(MockResponse.Builder().code(500).body("""{"error": "temporary failure"}""").build())
        viewModel.create {}
        runBlocking {
            withTimeout(10_000) { viewModel.state.first { (it as? NewChatUiState.Loaded)?.toolsFailure != null } }
        }

        var createdId: String? = null
        viewModel.openAnyway { createdId = it }

        assertEquals("new-conv-4", createdId)
        // 4 load GETs + POST create + failed PUT — openAnyway itself never touches the network.
        assertEquals(6, server.requestCount)
    }
}
