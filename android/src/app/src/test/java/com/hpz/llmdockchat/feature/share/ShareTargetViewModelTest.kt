package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.model.UrlFetchFailure
import com.hpz.llmdockchat.data.model.UrlFetchServer
import com.hpz.llmdockchat.data.model.UrlRetrieval
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
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import java.nio.file.Files

/** The share-target picker's four states. */
class ShareTargetViewModelTest {

    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    private lateinit var server: MockWebServer
    private lateinit var viewModel: ShareTargetViewModel
    private lateinit var repository: ConversationsRepository
    private lateinit var store: SharedDraftStore
    private lateinit var launcher: StubLauncher

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
        repository = ConversationsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        store = SharedDraftStore(Files.createTempDirectory("shared-drafts").toFile())
        launcher = StubLauncher(UrlRetrieval(true, listOf(UrlFetchServer("webfetch", "WebFetch", listOf("fetch_readable"))), emptyList()))
        viewModel = ShareTargetViewModel(repository, store, launcher)
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun settled(): ShareTargetUiState = runBlocking {
        withTimeout(10_000) {
            viewModel.state.first { it !is ShareTargetUiState.Loading }
        }
    }

    @Test
    fun `starts loading, then populates from the server with the staged share`() {
        assertTrue(viewModel.state.value is ShareTargetUiState.Loading)
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(text = "hello"))

        viewModel.refresh()
        val state = settled() as ShareTargetUiState.Loaded

        assertEquals(2, state.conversations.size)
        assertEquals("hello", state.share.text)
        assertFalse(state.isEmpty)
    }

    @Test
    fun `an empty list is the empty state, not an error`() {
        server.enqueue(MockResponse.Builder().body("""{"conversations": [], "total": 0}""").build())

        viewModel.refresh()
        val state = settled() as ShareTargetUiState.Loaded
        assertTrue(state.isEmpty)
    }

    @Test
    fun `a failing server is the failed state`() {
        server.enqueue(MockResponse.Builder().code(503).body("""{"error": "Docker socket unavailable"}""").build())

        viewModel.refresh()
        val state = settled()
        assertTrue(state is ShareTargetUiState.Failed)
        assertEquals("Docker socket unavailable", (state as ShareTargetUiState.Failed).message)
    }

    @Test
    fun `an unsupported share is carried into the loaded state, not an error`() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(error = "PDFs can't be shared into a chat"))

        viewModel.refresh()
        val state = settled() as ShareTargetUiState.Loaded

        assertEquals("PDFs can't be shared into a chat", state.share.error)
        assertEquals(2, state.conversations.size)
    }

    @Test
    fun `a second share while the picker is open replaces the staged content`() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(text = "first"))
        viewModel.refresh()
        settled()

        store.stage(StagedShare(text = "second"))
        val state = runBlocking {
            withTimeout(10_000) { viewModel.state.first { (it as ShareTargetUiState.Loaded).share.text == "second" } }
        } as ShareTargetUiState.Loaded
        assertEquals("second", state.share.text)
    }

    private fun stubProbe(retrieval: UrlRetrieval) {
        launcher = StubLauncher(retrieval)
        viewModel = ShareTargetViewModel(repository, store, launcher)
    }

    private fun stubProbeFailure() {
        launcher = StubLauncher(throwing = true)
        viewModel = ShareTargetViewModel(repository, store, launcher)
    }

    private fun stubOutcome(outcome: SummarizeOutcome) {
        launcher = StubLauncher(UrlRetrieval(true, listOf(UrlFetchServer("webfetch", "WebFetch", emptyList())), emptyList()), outcome)
        viewModel = ShareTargetViewModel(repository, store, launcher)
    }

    /** A shared link and a server that can fetch it: the action is offered. */
    @Test
    fun `a shared link offers summarize when a server can fetch it`() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(text = "look: https://example.com/a", url = "https://example.com/a"))

        viewModel.refresh()
        val state = settled() as ShareTargetUiState.Loaded

        assertEquals(SummarizeOption.Ready("https://example.com/a", listOf("webfetch")), state.summarize)
    }

    /** No link in the share, no action at all. */
    @Test
    fun `a share without a link offers no summarize action`() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(text = "plain prose about something else"))

        viewModel.refresh()

        assertEquals(SummarizeOption.NotShared, (settled() as ShareTargetUiState.Loaded).summarize)
    }

    /** Nothing configured blocks the action with what to do about it. */
    @Test
    fun `no page-fetch tool blocks the action with what to do about it`() {
        stubProbe(UrlRetrieval(supported = true, servers = emptyList(), failures = emptyList()))
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(text = "https://example.com/a", url = "https://example.com/a"))

        viewModel.refresh()
        val summarize = (settled() as ShareTargetUiState.Loaded).summarize

        assertTrue(summarize is SummarizeOption.Blocked && summarize.reason.contains("No tool"))
    }

    /** An old dashboard must not read as "nothing is configured" — different fix. */
    @Test
    fun `a dashboard that cannot answer the probe says so differently`() {
        stubProbe(UrlRetrieval.UNSUPPORTED)
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(text = "https://example.com/a", url = "https://example.com/a"))

        viewModel.refresh()
        val summarize = (settled() as ShareTargetUiState.Loaded).summarize

        assertTrue(summarize is SummarizeOption.Blocked && summarize.reason.contains("can't report"))
    }

    /** Configured but not answering is a third message, naming the server. */
    @Test
    fun `a page tool that did not answer is named`() {
        stubProbe(UrlRetrieval(true, emptyList(), listOf(UrlFetchFailure("webfetch", "timed out after 5s"))))
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(text = "https://example.com/a", url = "https://example.com/a"))

        viewModel.refresh()
        val summarize = (settled() as ShareTargetUiState.Loaded).summarize

        assertTrue(summarize is SummarizeOption.Blocked && summarize.reason.contains("webfetch"))
    }

    /** The probe request itself failing is not the same as having no tool. */
    @Test
    fun `a probe request that fails blocks with a retry`() {
        stubProbeFailure()
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(text = "https://example.com/a", url = "https://example.com/a"))

        viewModel.refresh()
        val summarize = (settled() as ShareTargetUiState.Loaded).summarize

        assertEquals(SummarizeOption.UNREACHABLE, summarize)
    }

    /** No usable model: the sheet takes over and the share survives. */
    @Test
    fun `a missing model choice keeps the share staged`() {
        stubOutcome(SummarizeOutcome.ChooseModel)
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(text = "https://example.com/a", url = "https://example.com/a"))
        viewModel.refresh()
        settled()

        var choseModel = false
        viewModel.summarize(onOpened = { error("must not open a thread") }, onChooseModel = { choseModel = true })

        assertTrue(choseModel)
        assertEquals("https://example.com/a", store.pending.value?.url)
        assertEquals("https://example.com/a", launcher.launchedWith?.first)
    }

    /** A failed launch leaves the reason on the picker and files nothing. */
    @Test
    fun `a failed launch shows the reason and files no claim`() {
        stubOutcome(SummarizeOutcome.Failed("Nope"))
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(text = "https://example.com/a", url = "https://example.com/a"))
        viewModel.refresh()
        settled()

        viewModel.summarize(onOpened = { error("must not open a thread") }, onChooseModel = { error("must not switch") })
        val state = viewModel.state.value as ShareTargetUiState.Loaded

        assertEquals("Nope", state.actionError)
        assertEquals(SummarizeOption.Ready("https://example.com/a", listOf("webfetch")), state.summarize)
        assertTrue(store.pending.value != null)
    }

    /** The tap hands the launcher the url and exactly the servers the probe named. */
    @Test
    fun `the tap passes the url and the servers the probe named`() {
        stubOutcome(SummarizeOutcome.Opened("conv-1"))
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        store.stage(StagedShare(text = "https://example.com/a", url = "https://example.com/a"))
        viewModel.refresh()
        settled()

        var opened: String? = null
        viewModel.summarize(onOpened = { opened = it }, onChooseModel = { error("must not switch") })

        assertEquals("conv-1", opened)
        assertEquals(listOf("webfetch"), launcher.launchedWith?.second)
    }

    @Test
    fun `rows are in the server's order - updated_at DESC, most recent first`() {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        viewModel.refresh()
        val state = settled() as ShareTargetUiState.Loaded

        val first = state.conversations[0]
        val second = state.conversations[1]
        assertTrue(first.updatedAt!! > second.updatedAt!!)
    }
}

/** Stands in for [SummarizeCoordinator]; records what the tap asked for. */
private class StubLauncher(
    private val retrieval: UrlRetrieval = UrlRetrieval.UNSUPPORTED,
    private val outcome: SummarizeOutcome = SummarizeOutcome.ChooseModel,
    private val throwing: Boolean = false,
) : SummarizeLauncher {
    var launchedWith: Pair<String, List<String>>? = null

    override suspend fun probe(): Result<UrlRetrieval> =
        if (throwing) Result.failure(RuntimeException("unreachable")) else Result.success(retrieval)

    override suspend fun launch(url: String, serverIds: List<String>): SummarizeOutcome {
        launchedWith = url to serverIds
        return outcome
    }
}
