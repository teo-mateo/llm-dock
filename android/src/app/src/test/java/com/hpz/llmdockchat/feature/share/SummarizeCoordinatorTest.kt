package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.testing.FakeNewChatPreferences
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.nio.file.Files

/**
 * The direct summarize path (F14-R7): one create, one tools write, one claim —
 * and nothing at all when either write fails, because a thread without its
 * fetcher would answer the instruction from the URL alone.
 */
class SummarizeCoordinatorTest {

    private lateinit var server: MockWebServer
    private lateinit var store: SharedDraftStore
    private lateinit var preferences: FakeNewChatPreferences
    private lateinit var api: ApiClient
    private lateinit var coordinator: SummarizeCoordinator

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        store = SharedDraftStore(Files.createTempDirectory("shared-drafts").toFile())
        preferences = FakeNewChatPreferences(RUNNING, initialMcpServerIds = listOf("sympy-math"))
        val urlStore = FakeServerUrlStore(
            (BaseUrl.normalize(server.url("/").toString()) as BaseUrlResult.Valid).baseUrl,
        )
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .build()
        api = ApiClient(client, urlStore, ApiJson, Dispatchers.IO)
        coordinator = coordinatorWith(preferences)
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun enqueue(
        services: String = readFixture("services_list.json"),
        openRouter: String = readFixture("openrouter_models.json"),
    ) {
        server.enqueue(MockResponse.Builder().body(services).build())
        server.enqueue(MockResponse.Builder().body(openRouter).build())
    }

    /** A coordinator with its own preferences — the ladder under test starts from them. */
    private fun coordinatorWith(prefs: FakeNewChatPreferences) = SummarizeCoordinator(
        servicesRepository = ServicesRepository(api),
        openRouterModelsRepository = OpenRouterModelsRepository(api),
        mcpServersRepository = McpServersRepository(api),
        conversationsRepository = ConversationsRepository(api),
        preferences = prefs,
        store = store,
    )

    private fun SummarizeCoordinator.launchSummarize() = runBlocking { launch(URL, listOf("webfetch")) }

    private fun launch(prefs: FakeNewChatPreferences = preferences): SummarizeOutcome =
        coordinatorWith(prefs).launchSummarize()

    private fun claim(): String? = runBlocking { store.takeAutoSend(NEW_ID) }

    private fun requests(): List<RecordedRequest> = List(server.requestCount) { server.takeRequest() }

    @Test
    fun `a happy launch files one claim for the thread it created`() {
        store.stage(StagedShare(text = URL, url = URL))
        enqueue()
        server.enqueue(MockResponse.Builder().body("""{"id":"$NEW_ID"}""").build())
        server.enqueue(MockResponse.Builder().body("""{"id":"$NEW_ID"}""").build())

        assertEquals(SummarizeOutcome.Opened(NEW_ID), launch())

        assertTrue(store.pending.value == null)
        val filed = claim()
        assertTrue(filed != null && filed.contains(URL))
        assertNull(claim())
    }

    @Test
    fun `the create names the remembered model and the tools write names the fetcher`() {
        store.stage(StagedShare(text = URL, url = URL))
        enqueue()
        server.enqueue(MockResponse.Builder().body("""{"id":"$NEW_ID"}""").build())
        server.enqueue(MockResponse.Builder().body("""{"id":"$NEW_ID"}""").build())

        launch()

        val calls = requests()
        assertEquals(4, calls.size)
        assertTrue(calls[2].url.encodedPath.endsWith("/api/chat/conversations"))
        assertTrue(calls[2].body!!.utf8().contains(""""main_service":"$RUNNING""""))
        assertTrue(calls[3].body!!.utf8().contains("webfetch"))
    }

    /** Summarizing a page must not decide what the next ordinary chat opens with. */
    @Test
    fun `a summarize leaves the remembered model and tools alone`() {
        store.stage(StagedShare(text = URL, url = URL))
        enqueue()
        server.enqueue(MockResponse.Builder().body("""{"id":"$NEW_ID"}""").build())
        server.enqueue(MockResponse.Builder().body("""{"id":"$NEW_ID"}""").build())

        launch()

        assertEquals(RUNNING, preferences.rememberedModel)
        assertEquals(listOf("sympy-math"), preferences.rememberedMcpServerIds)
    }

    @Test
    fun `no remembered model asks for a choice and creates nothing`() {
        enqueue()

        assertEquals(SummarizeOutcome.ChooseModel, launch(FakeNewChatPreferences()))

        assertEquals(2, server.requestCount)
        assertNull(claim())
    }

    /** F14-R5 — a stopped remembered model is a choice, not a dead thread. */
    @Test
    fun `a stopped remembered model asks for a choice`() {
        enqueue()

        assertEquals(SummarizeOutcome.ChooseModel, launch(FakeNewChatPreferences("vllm-qwen3-6-27b-fp8")))

        assertEquals(2, server.requestCount)
    }

    @Test
    fun `a failed create files no claim`() {
        store.stage(StagedShare(text = URL, url = URL))
        enqueue()
        server.enqueue(MockResponse.Builder().code(500).body("""{"error":"nope"}""").build())

        assertTrue(launch() is SummarizeOutcome.Failed)

        assertNull(claim())
        assertEquals(3, server.requestCount)
    }

    /** F14-R3 — tools are the precondition, so a failed tools write sends nothing. */
    @Test
    fun `a failed tools write files no claim`() {
        store.stage(StagedShare(text = URL, url = URL))
        enqueue()
        server.enqueue(MockResponse.Builder().body("""{"id":"$NEW_ID"}""").build())
        server.enqueue(MockResponse.Builder().code(403).body("""{"error":"forbidden"}""").build())

        val outcome = launch()

        assertTrue(outcome is SummarizeOutcome.Failed)
        assertTrue((outcome as SummarizeOutcome.Failed).message.contains("couldn't be enabled"))
        assertNull(claim())
    }

    @Test
    fun `the probe asks the dashboard for the capability, not the server names`() {
        server.enqueue(
            MockResponse.Builder().body(
                """{"servers": [], "url_fetch": {"available": true, "servers": [{"id": "webfetch", "name": "WebFetch", "tools": ["fetch_readable"]}], "failures": []}}""",
            ).build(),
        )

        val retrieval = runBlocking { coordinator.probe().getOrThrow() }

        assertTrue(retrieval.isAvailable)
        assertEquals(listOf("webfetch"), retrieval.serverIds)
        assertTrue(server.takeRequest().url.toString().contains("probe=url-fetch"))
    }

    private companion object {
        const val URL = "https://example.com/a"
        const val RUNNING = "llamacpp-gemma-4-26b-a4b-it-q8"
        const val NEW_ID = "new-conv-1"
    }
}
