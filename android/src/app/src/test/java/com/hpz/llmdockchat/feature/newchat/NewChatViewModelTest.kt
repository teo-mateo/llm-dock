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
import com.hpz.llmdockchat.data.model.ServiceSummary
import com.hpz.llmdockchat.feature.modelpicker.runningChatCapable
import com.hpz.llmdockchat.testing.FakeNewChatPreferences
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.MainDispatcherRule
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.CompletableDeferred
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

    private fun viewModel(preselectedServiceName: String? = null) = NewChatViewModel(
        servicesRepository = servicesRepository,
        promptsRepository = promptsRepository,
        mcpServersRepository = mcpServersRepository,
        openRouterModelsRepository = openRouterModelsRepository,
        conversationsRepository = conversationsRepository,
        preferences = preferences,
        servicesStreamRepository = servicesStreamRepository,
        preselectedServiceName = preselectedServiceName,
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
        // #269: the three engines the baseline classified as unknown now flow
        // through the chat-capable filter, on their template_type and prefix.
        assertTrue(names.contains("ik-qwen3.6-27b-iq4xs"))
        assertTrue(names.contains("exl3-gemma-4-31b-it"))
        assertTrue(names.contains("ninfer-qwen3.8-27b-nvfp4"))
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
        assertFalse(state.modelUnavailable)
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
        assertTrue(state.modelUnavailable)
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
        assertTrue(state.modelUnavailable)
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
        assertFalse(state.modelUnavailable)
    }

    /**
     * F10-R6: the Models tab's "New chat" action passes a specific running
     * service, which must win over whatever [preferences] remembered from
     * last time — that is the entire point of tapping it from a particular row.
     */
    @Test
    fun `a preselected running service wins over whatever was remembered`() {
        preferences = FakeNewChatPreferences(initialModel = "vllm-qwen3-6-27b-fp8") // exited in the fixture
        enqueueLoadResponses()
        val viewModel = viewModel(preselectedServiceName = "llamacpp-gemma-4-26b-a4b-it-q8")

        viewModel.load()
        val state = settled(viewModel) as NewChatUiState.Loaded

        val selected = state.selectedModel as ModelOption.LocalService
        assertEquals("llamacpp-gemma-4-26b-a4b-it-q8", selected.serviceName)
        assertFalse(state.modelUnavailable) // the preselect resolved cleanly; nothing here was "unavailable"
    }

    /**
     * If the tapped service stopped running between the tap and the sheet
     * loading, the preselect must not land on a dead service — it falls
     * through to the ordinary remembered-model resolution instead of
     * crashing or silently picking a stopped row.
     */
    @Test
    fun `a preselected service that stopped running falls back to the remembered-model resolution`() {
        preferences = FakeNewChatPreferences(initialModel = "llamacpp-gemma-4-26b-a4b-it-q8")
        enqueueLoadResponses()
        val viewModel = viewModel(preselectedServiceName = "vllm-qwen3-6-27b-fp8") // exited in the fixture

        viewModel.load()
        val state = settled(viewModel) as NewChatUiState.Loaded

        val selected = state.selectedModel as ModelOption.LocalService
        assertEquals("llamacpp-gemma-4-26b-a4b-it-q8", selected.serviceName)
    }

    @Test
    fun `no remembered model at all leaves the sheet requiring an explicit choice`() {
        enqueueLoadResponses()
        val viewModel = viewModel()

        viewModel.load()
        val state = settled(viewModel) as NewChatUiState.Loaded

        assertNull(state.selectedModel)
        assertFalse(state.modelUnavailable) // nothing was remembered — not "unavailable"
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

        val created = CompletableDeferred<String>()
        viewModel.create { created.complete(it) }

        // Await the callback, not a state emission. `applyTools` emits its
        // final state *before* invoking onCreated, so a `state.first { … &&
        // createdId != null }` can only pass when the collector happens to
        // start after the whole coroutine has finished — a scheduling
        // coin-flip that failed in CI at the 10 s timeout.
        val createdId = runBlocking { withTimeout(10_000) { created.await() } }
        val finalState = viewModel.state.value
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
        val retried = CompletableDeferred<String>()
        viewModel.retryTools { retried.complete(it) }

        // As above: await the callback itself. `state.first { createdId !=
        // null }` is racy here because the callback fires after the last
        // emission, so the predicate is only ever true on the value the
        // collector starts with.
        val createdId = runBlocking { withTimeout(10_000) { retried.await() } }
        val finalState = viewModel.state.value
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

    // ---- Issue 266: the live stream owns what may start a chat ----

    private val selectedRunningGemma = "llamacpp-gemma-4-26b-a4b-it-q8"

    private fun serviceRow(name: String, status: String = "running", kind: String = "chat") =
        """{"name":"$name","status":"$status","kind":"$kind","host_port":3302,"favorite":false}"""

    private fun snapshotFrame(vararg rows: String) =
        """{"type":"snapshot","data":{"services":[${rows.joinToString(",")}],"total":${rows.size},"running":0,"stopped":0}}"""

    private fun deltaFrame(name: String, status: String) =
        """{"type":"delta","service_name":"$name","status":"$status"}"""

    /** Like the delta test above: wait for the exact outcome, never for a first settled value. */
    private fun awaitLoaded(viewModel: NewChatViewModel, predicate: (NewChatUiState.Loaded) -> Boolean): NewChatUiState.Loaded =
        runBlocking {
            withTimeout(10_000) {
                viewModel.state.first { (it as? NewChatUiState.Loaded)?.let(predicate) == true }
            }
        } as NewChatUiState.Loaded

    /**
     * AC 1. The sheet opens with the remembered running model selected, the
     * stream's first snapshot confirms it, then a delta stops it — Start goes
     * off and the sheet asks for a new model (issue 266).
     */
    @Test
    fun `a delta stopping the selected service disables Start and asks for a new model`() {
        preferences = FakeNewChatPreferences(initialModel = selectedRunningGemma)
        enqueueLoadResponses()
        servicesStreamTransport.payloads = listOf(
            snapshotFrame(serviceRow(selectedRunningGemma)),
            deltaFrame(selectedRunningGemma, "exited"),
        )
        val viewModel = viewModel()

        viewModel.load()
        val state = awaitLoaded(viewModel) { it.selectedModel == null && it.modelUnavailable }

        assertFalse(state.canStart)
    }

    /**
     * AC 1 + AC 5. The invalidation clears the model row only: the tool
     * selection rides through it untouched, and the prompt and summarize rows
     * keep their values (the pure [reconcileLiveServices] test pins the full
     * set, since scripted transport frames all land inside one `load()` here).
     */
    @Test
    fun `a delta stopping the selected service preserves the prompt and tool selections`() {
        preferences = FakeNewChatPreferences(
            initialModel = selectedRunningGemma,
            initialMcpServerIds = listOf("sympy-math"),
        )
        enqueueLoadResponses()
        servicesStreamTransport.payloads = listOf(
            snapshotFrame(serviceRow(selectedRunningGemma)),
            deltaFrame(selectedRunningGemma, "exited"),
        )
        val viewModel = viewModel()

        viewModel.load()
        val state = awaitLoaded(viewModel) { it.selectedModel == null && it.modelUnavailable }

        assertEquals(setOf("sympy-math"), state.selectedMcpServerIds)
        assertNull(state.selectedPromptId)
        assertNull(state.summarizeUrl)
    }

    /** AC 1. Removal arrives as absence from the next snapshot, not a delta. */
    @Test
    fun `a service absent from a later snapshot invalidates the selection`() {
        preferences = FakeNewChatPreferences(initialModel = selectedRunningGemma)
        enqueueLoadResponses()
        servicesStreamTransport.payloads = listOf(
            snapshotFrame(serviceRow(selectedRunningGemma)),
            snapshotFrame(serviceRow("vllm-qwen3-6-27b-fp8")),
        )
        val viewModel = viewModel()

        viewModel.load()
        val state = awaitLoaded(viewModel) {
            it.selectedModel == null && it.modelUnavailable && it.services.none { s -> s.name == selectedRunningGemma }
        }

        assertFalse(state.canStart)
    }

    /** AC 1. A row that stays running but stops being chat-capable is just as dead for a thread. */
    @Test
    fun `a snapshot making the selected service non-chat invalidates the selection`() {
        preferences = FakeNewChatPreferences(initialModel = selectedRunningGemma)
        enqueueLoadResponses()
        servicesStreamTransport.payloads = listOf(
            snapshotFrame(serviceRow(selectedRunningGemma)),
            snapshotFrame(serviceRow(selectedRunningGemma, kind = "embedding")),
        )
        val viewModel = viewModel()

        viewModel.load()
        val state = awaitLoaded(viewModel) { it.selectedModel == null && it.modelUnavailable }

        assertTrue(state.services.any { s -> s.name == selectedRunningGemma && s.status == "running" })
        assertFalse(state.canStart)
    }

    /** AC 4. A local stop lands; the OpenRouter selection doesn't notice (issue 266). */
    @Test
    fun `a remote selection survives local status deltas`() {
        preferences = FakeNewChatPreferences(initialModel = "openrouter:someone/retired-model")
        enqueueLoadResponses()
        servicesStreamTransport.payloads = listOf(
            snapshotFrame(serviceRow(selectedRunningGemma)),
            deltaFrame(selectedRunningGemma, "exited"),
        )
        val viewModel = viewModel()

        viewModel.load()
        val state = awaitLoaded(viewModel) { loaded ->
            loaded.selectedModel is ModelOption.Remote &&
                loaded.services.none { s -> s.name == selectedRunningGemma && s.status == "running" }
        }

        assertEquals("someone/retired-model", (state.selectedModel as ModelOption.Remote).modelId)
        assertFalse(state.modelUnavailable)
        assertTrue(state.canStart)
    }

    /**
     * AC 2. running → exited → running: the invalidation is sticky (no
     * auto-reselection), but the row is back in the picker and a fresh
     * selection re-enables Start.
     */
    @Test
    fun `the same service starting again is selectable and Start re-enables`() {
        preferences = FakeNewChatPreferences(initialModel = selectedRunningGemma)
        enqueueLoadResponses()
        servicesStreamTransport.payloads = listOf(
            snapshotFrame(serviceRow(selectedRunningGemma)),
            deltaFrame(selectedRunningGemma, "exited"),
            deltaFrame(selectedRunningGemma, "running"),
        )
        val viewModel = viewModel()

        viewModel.load()
        val state = awaitLoaded(viewModel) { loaded ->
            loaded.selectedModel == null && loaded.modelUnavailable &&
                runningChatCapable(loaded.services).any { it.name == selectedRunningGemma }
        }
        assertFalse(state.canStart)

        viewModel.selectModel(ModelOption.LocalService(selectedRunningGemma, "running"))
        val picked = viewModel.state.value as NewChatUiState.Loaded
        assertFalse(picked.modelUnavailable)
        assertTrue(picked.canStart)
    }

    /**
     * AC 3. The probe's exact shape: `selectedModel` still carries the
     * `running` status captured at pick time while the live row is `exited` —
     * `create()` refuses it and invalidates instead of POSTing a dead thread.
     */
    @Test
    fun `create sends nothing when the selection is stale`() {
        enqueueLoadResponses()
        val viewModel = viewModel()
        viewModel.load()
        settled(viewModel)

        // vllm-qwen3-6-27b-fp8 is "exited" in the services fixture; selectModel
        // is reachable only with picker rows (running), so a stale capture is
        // set up directly — the state a stop that landed after the pick leaves.
        viewModel.selectModel(ModelOption.LocalService("vllm-qwen3-6-27b-fp8", "running"))

        var created = false
        viewModel.create { created = true }

        val state = viewModel.state.value as NewChatUiState.Loaded
        assertFalse(created)
        assertFalse(state.creating)
        assertNull(state.selectedModel)
        assertTrue(state.modelUnavailable)
        assertFalse(state.canStart)
        // The 4 load GETs only — create() refused before sending anything.
        assertEquals(4, server.requestCount)
    }

    /** AC 1 + AC 4, pure: the captured status is never consulted — the live row decides. */
    @Test
    fun `isLiveSelectable refuses a captured running status against an exited live row`() {
        val exited = ServiceSummary(name = "llamacpp-gemma-4-31b-it-q8", status = "exited", kind = "chat")
        val running = exited.copy(status = "running")
        val notChat = running.copy(kind = "embedding")

        assertFalse(ModelOption.LocalService(exited.name, "running").isLiveSelectable(listOf(exited)))
        assertTrue(ModelOption.LocalService(exited.name, "exited").isLiveSelectable(listOf(running)))
        assertFalse(ModelOption.LocalService(exited.name, "running").isLiveSelectable(listOf(notChat)))
        assertFalse(ModelOption.LocalService(exited.name, "running").isLiveSelectable(emptyList()))
        assertTrue(ModelOption.Remote("deepseek/deepseek-v4-flash", "DeepSeek V4 Flash").isLiveSelectable(emptyList()))
        assertFalse((null as ModelOption?).isLiveSelectable(listOf(running)))
    }

    /** AC 5, pure: the invalidation clears the model row and nothing else. */
    @Test
    fun `reconcileLiveServices refreshes a valid selection and leaves every other row untouched`() {
        val selection = ModelOption.LocalService(selectedRunningGemma, "exited")
        val loaded = NewChatUiState.Loaded(
            localServices = listOf(selection),
            services = listOf(ServiceSummary(selectedRunningGemma, "exited", "chat")),
            remoteModels = emptyList(),
            remoteModelsConfigured = false,
            selectedModel = selection,
            modelUnavailable = false,
            prompts = emptyList(),
            selectedPromptId = "prompt-7",
            mcpServers = emptyList(),
            selectedMcpServerIds = setOf("sympy-math"),
            requiredMcpServerIds = setOf("render-html"),
            summarizeUrl = "https://example.com/article",
            toolsFailure = ToolsFailure("conv-9", "tools PUT failed"),
        )

        val revived = reconcileLiveServices(loaded, listOf(ServiceSummary(selectedRunningGemma, "running", "chat")))
        assertEquals(ModelOption.LocalService(selectedRunningGemma, "running"), revived.selectedModel)
        assertFalse(revived.modelUnavailable)
        assertEquals("prompt-7", revived.selectedPromptId)
        assertEquals(setOf("sympy-math"), revived.selectedMcpServerIds)
        assertEquals(setOf("render-html"), revived.requiredMcpServerIds)
        assertEquals("https://example.com/article", revived.summarizeUrl)
        assertEquals(loaded.toolsFailure, revived.toolsFailure)

        val invalidated = reconcileLiveServices(loaded, listOf(ServiceSummary(selectedRunningGemma, "exited", "chat")))
        assertNull(invalidated.selectedModel)
        assertTrue(invalidated.modelUnavailable)
        assertFalse(invalidated.canStart)
        assertEquals("prompt-7", invalidated.selectedPromptId)
        assertEquals(setOf("sympy-math"), invalidated.selectedMcpServerIds)
        assertEquals(setOf("render-html"), invalidated.requiredMcpServerIds)
        assertEquals("https://example.com/article", invalidated.summarizeUrl)
        assertEquals(loaded.toolsFailure, invalidated.toolsFailure)
    }
}
