package com.hpz.llmdockchat.feature.logs

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.core.net.LogStreamEvent
import com.hpz.llmdockchat.data.LogsStreamRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.model.LogLevel
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.MainDispatcherRule
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

/**
 * F12-R1's frame handling, F12-R3's fallback, and F12-R4's level tagging —
 * driven directly against the ViewModel's event API rather than through
 * [LogsStreamRepository]'s flow machinery, which [LogsStreamRepositoryTest]
 * already covers. This is exactly what [LogsScreen]'s collector calls, so it
 * exercises the same state machine [LogsScreen] would.
 */
class LogsViewModelTest {

    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    private lateinit var server: MockWebServer
    private lateinit var servicesRepository: ServicesRepository

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
        servicesRepository = ServicesRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun viewModel() = LogsViewModel(
        serviceName = "llamacpp-a",
        logsStreamRepository = LogsStreamRepository(FakeSseTransport()),
        servicesRepository = servicesRepository,
    )

    @Test
    fun `snapshot then log lines then snapshot_end place the boundary after the tail`() {
        val vm = viewModel()

        vm.onStreamEvent(LogStreamEvent.SnapshotStart)
        vm.onStreamEvent(LogStreamEvent.Log("line one"))
        vm.onStreamEvent(LogStreamEvent.Log("line two"))
        vm.onStreamEvent(LogStreamEvent.SnapshotEnd)

        val state = vm.state.value as LogsUiState.Loaded
        assertEquals(listOf("line one", "line two"), state.lines.map { it.text })
        assertEquals(2, state.boundaryIndex)
        assertEquals(LogsConnection.LIVE, state.connection)
    }

    /** F12-R4: a line with no recognisable level renders plainly, not crashing or vanishing. */
    @Test
    fun `an ERROR line is tagged, a plain line degrades to plain`() {
        val vm = viewModel()

        vm.onStreamEvent(LogStreamEvent.Log("ERROR: could not bind port"))
        vm.onStreamEvent(LogStreamEvent.Log("Loading safetensors shards: 33%"))

        val lines = (vm.state.value as LogsUiState.Loaded).lines
        assertEquals(LogLevel.ERROR, lines[0].level)
        assertEquals(LogLevel.PLAIN, lines[1].level)
    }

    /**
     * Bug-shaped: a viewmodel that treats `stream_end` as an error would show
     * [LogsUiState.Failed] here, which is exactly what F12-R1's fourth
     * criterion says must not happen for a container that was simply stopped.
     */
    @Test
    fun `stream_end is an ended state, not a failure`() {
        val vm = viewModel()
        vm.onStreamEvent(LogStreamEvent.Log("last line before stop"))

        vm.onStreamEvent(LogStreamEvent.StreamEnd)

        val state = vm.state.value
        assertTrue(state is LogsUiState.Loaded)
        assertEquals(LogsConnection.ENDED, (state as LogsUiState.Loaded).connection)
    }

    /** The connection dropped without an explicit `stream_end` frame — same end state either way. */
    @Test
    fun `the flow completing without a stream_end frame is also treated as ended`() {
        val vm = viewModel()
        vm.onStreamEvent(LogStreamEvent.Log("one line"))

        vm.onStreamCompleted()

        val state = vm.state.value as LogsUiState.Loaded
        assertEquals(LogsConnection.ENDED, state.connection)
    }

    /**
     * Bug-shaped: a naive `onStreamFailed` that always shows a generic error
     * would leave a `not-created` service on a blank/wrong screen — F12-R1's
     * fifth criterion requires the dashboard's own 404 message specifically.
     */
    @Test
    fun `a 404 on the very first connection attempt is NotCreated, not Failed`() {
        val vm = viewModel()

        vm.onStreamFailed(fakeHttp404("Service has not been created yet"))

        val state = vm.state.value
        assertTrue(state is LogsUiState.NotCreated)
        assertEquals("Service has not been created yet", (state as LogsUiState.NotCreated).message)
    }

    /** F12-R3: the stream could not be established (not a 404) — falls back to the one-shot fetch. */
    @Test
    fun `a non-404 connection failure falls back to the one-shot fetch`() {
        server.enqueue(
            MockResponse.Builder().body(
                """{"service": "llamacpp-a", "logs": "one\ntwo", "lines": 2, "timestamp": "now"}""",
            ).build(),
        )
        val vm = viewModel()

        vm.onStreamFailed(RuntimeException("connection reset"))
        val state = settled(vm)

        assertTrue(state is LogsUiState.Loaded)
        val loaded = state as LogsUiState.Loaded
        assertEquals(listOf("one", "two"), loaded.lines.map { it.text })
        assertEquals(LogsConnection.FALLBACK, loaded.connection)
        assertNull(loaded.boundaryIndex)
    }

    @Test
    fun `when the fallback also fails, the failure is shown as-is`() {
        server.enqueue(MockResponse.Builder().code(500).body("""{"error": "Docker socket unavailable"}""").build())
        val vm = viewModel()

        vm.onStreamFailed(RuntimeException("connection reset"))
        val state = settled(vm)

        assertTrue(state is LogsUiState.Failed)
    }

    private fun settled(viewModel: LogsViewModel): LogsUiState = runBlocking {
        withTimeout(10_000) { viewModel.state.first { it !is LogsUiState.Loading } }
    }

    private fun fakeHttp404(message: String): Throwable =
        com.hpz.llmdockchat.core.net.ApiException(com.hpz.llmdockchat.core.error.AppError.Http(404, message, fromServer = true))
}
