package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.core.prefs.InMemorySummarizePreferences
import com.hpz.llmdockchat.core.prefs.SummarizeDefaults
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.testing.FakeDraftStore
import com.hpz.llmdockchat.testing.FakeNewChatPreferences
import com.hpz.llmdockchat.testing.FakeServerUrlStore
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
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import java.nio.file.Files

/**
 * The share-target picker's four states (F14-R2, F00-R5) and F16's summarize
 * row: when it appears, and what one tap does to the server — including the two
 * failures that must not send anything.
 */
class ShareTargetViewModelTest {

    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    private lateinit var server: MockWebServer
    private lateinit var api: ApiClient
    private lateinit var viewModel: ShareTargetViewModel
    private lateinit var store: SharedDraftStore
    private lateinit var drafts: FakeDraftStore
    private lateinit var summarize: InMemorySummarizePreferences
    private lateinit var newChatPreferences: FakeNewChatPreferences

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
        api = ApiClient(client, urlStore, ApiJson, Dispatchers.IO)
        store = SharedDraftStore(Files.createTempDirectory("shared-drafts").toFile())
        drafts = FakeDraftStore()
        summarize = InMemorySummarizePreferences()
        newChatPreferences = FakeNewChatPreferences(initialModel = RUNNING_MODEL)
        viewModel = buildViewModel()
    }

    /** Built apart from setUp so a test can vary the remembered model and keep one server. */
    private fun buildViewModel() = ShareTargetViewModel(
        repository = ConversationsRepository(api),
        store = store,
        drafts = drafts,
        servicesRepository = ServicesRepository(api),
        mcpServersRepository = McpServersRepository(api),
        summarizePreferences = summarize,
        newChatPreferences = newChatPreferences,
    )

    @After
    fun tearDown() {
        server.close()
    }

    private fun settled(): ShareTargetUiState = runBlocking {
        withTimeout(10_000) {
            viewModel.state.first { it !is ShareTargetUiState.Loading }
        }
    }

    private fun ok(body: String) = MockResponse.Builder().body(body).build()

    /** The registry read rides along with every refresh, and is served first. */
    private fun enqueueRegistry(body: String = readFixture("mcp_servers.json")) {
        server.enqueue(ok(body))
    }

    private fun loaded(): ShareTargetUiState.Loaded = settled() as ShareTargetUiState.Loaded

    // -- F14-R2: the picker's four states ----------------------------------

    @Test
    fun `starts loading, then populates from the server with the staged share`() {
        assertTrue(viewModel.state.value is ShareTargetUiState.Loading)
        enqueueRegistry()
        server.enqueue(ok(readFixture("conversations.json")))
        store.stage(StagedShare(text = "hello"))

        viewModel.refresh()
        val state = loaded()

        assertEquals(2, state.conversations.size)
        assertEquals("hello", state.share.text)
        assertFalse(state.isEmpty)
    }

    @Test
    fun `an empty list is the empty state, not an error`() {
        enqueueRegistry()
        server.enqueue(ok("""{"conversations": [], "total": 0}"""))

        viewModel.refresh()
        val state = loaded()
        assertTrue(state.isEmpty)
    }

    @Test
    fun `a failing server is the failed state`() {
        enqueueRegistry()
        server.enqueue(MockResponse.Builder().code(503).body("""{"error": "Docker socket unavailable"}""").build())

        viewModel.refresh()
        val state = settled()
        assertTrue(state is ShareTargetUiState.Failed)
        assertEquals("Docker socket unavailable", (state as ShareTargetUiState.Failed).message)
    }

    @Test
    fun `an unsupported share is carried into the loaded state, not an error`() {
        enqueueRegistry()
        server.enqueue(ok(readFixture("conversations.json")))
        store.stage(StagedShare(error = "PDFs can't be shared into a chat"))

        viewModel.refresh()
        val state = loaded()

        assertEquals("PDFs can't be shared into a chat", state.share.error)
        assertEquals(2, state.conversations.size)
    }

    @Test
    fun `a second share while the picker is open replaces the staged content`() {
        enqueueRegistry()
        server.enqueue(ok(readFixture("conversations.json")))
        store.stage(StagedShare(text = "first"))
        viewModel.refresh()
        settled()

        store.stage(StagedShare(text = "second"))
        val state = runBlocking {
            withTimeout(10_000) { viewModel.state.first { (it as ShareTargetUiState.Loaded).share.text == "second" } }
        } as ShareTargetUiState.Loaded
        assertEquals("second", state.share.text)
    }

    @Test
    fun `rows are in the server's order - updated_at DESC, most recent first`() {
        enqueueRegistry()
        server.enqueue(ok(readFixture("conversations.json")))
        viewModel.refresh()
        val state = loaded()

        val first = state.conversations[0]
        val second = state.conversations[1]
        assertTrue(first.updatedAt!! > second.updatedAt!!)
    }

    // -- F16-R1: row visibility ---------------------------------------------

    @Test
    fun `a shared link gets the row when the registry reports a fetch tool`() {
        openPicker(StagedShare(text = "worth reading https://example.com/a"))

        assertTrue(viewModel.state.value.let { (it as ShareTargetUiState.Loaded).canSummarize })
    }

    @Test
    fun `a share with no link gets no row`() {
        openPicker(StagedShare(text = "just prose, no link"))

        assertFalse(loaded().canSummarize)
    }

    @Test
    fun `an image share gets no row`() {
        openPicker(StagedShare(attachments = listOf("data:image/jpeg;base64,AAA"), origin = StagedOrigin.IMAGE))

        assertFalse(loaded().canSummarize)
    }

    @Test
    fun `a text file quoting a link gets no row`() {
        openPicker(
            StagedShare(text = "**Attached file: `x.md`**\n\nhttps://example.com", origin = StagedOrigin.TEXT_FILE),
        )

        assertFalse(loaded().canSummarize)
    }

    @Test
    fun `no fetch tool in the registry gets no row`() {
        openPicker(
            StagedShare(text = "https://example.com"),
            registry = """{"servers": [{"id": "sympy-math", "name": "SymPy", "description": "", "icon": "x"}]}""",
        )

        assertFalse(loaded().canSummarize)
        assertTrue(loaded().summarizeTools.isEmpty())
    }

    @Test
    fun `a share whose only web tool the registry still reports keeps the row`() {
        openPicker(
            StagedShare(text = "https://example.com"),
            registry = """{"servers": [{"id": "websearch", "name": "Web Search", "description": "", "icon": "x"}]}""",
        )

        assertEquals(listOf("websearch"), loaded().summarizeTools)
    }

    // -- F16-R2: one tap, three calls --------------------------------------

    @Test
    fun `one tap creates the thread, puts the tools on it, stages the message and arms the send`() = runBlocking {
        openPicker(StagedShare(text = "https://example.com/a"))
        server.enqueue(ok(readFixture("services_list.json")))
        server.enqueue(ok("""{"id": "new-sum-1"}"""))
        server.enqueue(ok("""{"id": "new-sum-1"}"""))

        viewModel.summarize()
        val launch = withTimeout(10_000) {
            viewModel.state.first { (it as? ShareTargetUiState.Loaded)?.launch != null }
        }
        val after = launch as ShareTargetUiState.Loaded

        assertEquals(SummarizeLaunch.Thread("new-sum-1"), after.launch)
        assertFalse(after.summarizing)
        // The composed instruction + URL, not the bare shared text.
        assertEquals("${SummarizeDefaults.PROMPT}\n\nhttps://example.com/a", drafts.saved["new-sum-1"])
        assertTrue(store.takeAutoSend("new-sum-1"))
        assertNull(store.pending.value)
        // Registry GET + list GET (the refresh) + services GET, then create, then PUT.
        drain(3)
        assertEquals("POST", server.takeRequest().method)
        assertEquals("PUT", server.takeRequest().method)
    }

    @Test
    fun `the tools PUT carries exactly the summarize ids`() = runBlocking {
        openPicker(StagedShare(text = "https://example.com/a"))
        server.enqueue(ok(readFixture("services_list.json")))
        server.enqueue(ok("""{"id": "new-sum-2"}"""))
        server.enqueue(ok("""{"id": "new-sum-2"}"""))

        viewModel.summarize()
        awaitLaunch()

        // The PUT is the last of the five: two reads for the refresh, one for
        // the gate, then the create, then this.
        drain(4)
        val putBody = server.takeRequest().body?.utf8().orEmpty()
        assertTrue(putBody.contains("webfetch"))
        assertTrue(putBody.contains("websearch"))
    }

    @Test
    fun `a failed create leaves the picker where it was, with the server's words and the share still staged`() {
        openPicker(StagedShare(text = "https://example.com/a"))
        server.enqueue(ok(readFixture("services_list.json")))
        server.enqueue(MockResponse.Builder().code(400).body("""{"error": "main_service is required"}""").build())

        viewModel.summarize()
        val state = runBlocking {
            withTimeout(10_000) { viewModel.state.first { (it as? ShareTargetUiState.Loaded)?.summarizeError != null } }
        } as ShareTargetUiState.Loaded

        assertEquals("main_service is required", state.summarizeError)
        assertFalse(state.summarizing)
        assertNull(state.launch)
        assertNotNull(store.pending.value)
        assertFalse(store.peekSummarize()?.message?.isNotBlank() == true)
        assertFalse(drafts.saved.containsKey("new-sum-1"))
    }

    @Test
    fun `a failed tools PUT opens the thread with the message staged and nothing armed to send`() = runBlocking {
        openPicker(StagedShare(text = "https://example.com/a"))
        server.enqueue(ok(readFixture("services_list.json")))
        server.enqueue(ok("""{"id": "new-sum-3"}"""))
        server.enqueue(MockResponse.Builder().code(500).body("""{"error": "nope"}""").build())

        viewModel.summarize()
        val launch = awaitLaunch()

        assertEquals(SummarizeLaunch.Thread("new-sum-3"), launch)
        assertEquals("${SummarizeDefaults.PROMPT}\n\nhttps://example.com/a", drafts.saved["new-sum-3"])
        assertFalse(store.takeAutoSend("new-sum-3"))
        assertEquals(SharedDraftStore.TOOLS_NOT_ENABLED_NOTICE, store.notice("new-sum-3"))
    }

    @Test
    fun `no remembered model arms the new-chat sheet and creates nothing`() = runBlocking {
        newChatPreferences = FakeNewChatPreferences(initialModel = null)
        viewModel = buildViewModel()
        openPicker(StagedShare(text = "https://example.com/a"))
        server.enqueue(ok(readFixture("services_list.json")))

        viewModel.summarize()
        val launch = awaitLaunch()

        assertEquals(SummarizeLaunch.NewChat, launch)
        assertEquals("${SummarizeDefaults.PROMPT}\n\nhttps://example.com/a", store.peekSummarize()?.message)
        assertEquals(listOf("webfetch", "websearch"), store.peekSummarize()?.toolIds)
        // Only the services read happened: no create, no PUT.
        assertEquals(3, server.requestCount)
    }

    @Test
    fun `a remembered model that stopped running falls through to the sheet`() = runBlocking {
        newChatPreferences = FakeNewChatPreferences(initialModel = "vllm-qwen3-6-27b-fp8")
        viewModel = buildViewModel()
        openPicker(StagedShare(text = "https://example.com/a"))
        server.enqueue(ok(readFixture("services_list.json")))

        viewModel.summarize()

        assertEquals(SummarizeLaunch.NewChat, awaitLaunch())
    }

    /** The picker's two reads (registry, then list), served in the order the refresh makes them. */
    private fun openPicker(share: StagedShare, registry: String = readFixture("mcp_servers.json")) {
        store.stage(share)
        enqueueRegistry(registry)
        server.enqueue(ok(readFixture("conversations.json")))
        viewModel.refresh()
        loaded()
    }

    private fun drain(count: Int) {
        repeat(count) { server.takeRequest() }
    }

    private suspend fun awaitLaunch(): SummarizeLaunch? = withTimeout(10_000) {
        viewModel.state.first { (it as? ShareTargetUiState.Loaded)?.launch != null }
            .let { (it as ShareTargetUiState.Loaded).launch }
    }

    private companion object {
        const val RUNNING_MODEL = "llamacpp-gemma-4-26b-a4b-it-q8"
    }
}
