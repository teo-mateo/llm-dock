package com.hpz.llmdockchat.feature.models

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.data.GpuStreamRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.data.model.GpuState
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.MainDispatcherRule
import com.hpz.llmdockchat.testing.ScriptedSseTransport
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.DelicateCoroutinesApi
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

/**
 * F10-R1's grouping and initial load (via [ModelsUiState.Loaded]),
 * F10-R1's fifth criterion (stale on a dropped stream) and F10-R3 (GPU state
 * flowing through). The teardown mechanism — F10-R3's third criterion — is
 * covered separately in [ModelsViewModelTeardownTest], which needs real
 * cancellation rather than [MainDispatcherRule]'s unconfined dispatcher.
 */
class ModelsViewModelTest {

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
        val api = ApiClient(client, urlStore, ApiJson, Dispatchers.IO)
        servicesRepository = ServicesRepository(api)
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun viewModel(
        servicesStreamTransport: FakeSseTransport = FakeSseTransport(),
        gpuStreamTransport: FakeSseTransport = FakeSseTransport(),
    ) = ModelsViewModel(
        servicesRepository = servicesRepository,
        servicesStreamRepository = ServicesStreamRepository(servicesStreamTransport),
        gpuStreamRepository = GpuStreamRepository(gpuStreamTransport),
    )

    private fun settled(viewModel: ModelsViewModel): ModelsUiState = runBlocking {
        withTimeout(10_000) { viewModel.state.first { it !is ModelsUiState.Loading } }
    }

    /**
     * What [com.hpz.llmdockchat.feature.models.ModelsScreen]'s two
     * `LaunchedEffect`s do — collect the live streams and feed them back into
     * the ViewModel. Production owns this at the composition boundary (see
     * [ModelsViewModel]'s class doc for why); a plain unit test has no
     * composition, so it wires the same two lines by hand.
     */
    @OptIn(DelicateCoroutinesApi::class)
    private fun ModelsViewModel.startStreamsLikeTheScreenWould() {
        GlobalScope.launch(Dispatchers.Main) { observeServicesStream().collect { applyServicesUpdate(it) } }
        GlobalScope.launch(Dispatchers.Main) { observeGpuStream().collect { applyGpuUpdate(it) } }
    }

    @Test
    fun `running services are grouped first, stopped second, each in the payload's host-port order`() {
        server.enqueue(MockResponse.Builder().body(readFixture("services_list.json")).build())
        val viewModel = viewModel()

        viewModel.start()
        val state = settled(viewModel) as ModelsUiState.Loaded

        // Fixture: open-webui (3300) and llamacpp-gemma-4-26b-a4b-it-q8 (3301)
        // are the only two "running" rows; everything else is exited/not-created.
        assertEquals(listOf("open-webui", "llamacpp-gemma-4-26b-a4b-it-q8"), state.running.map { it.name })
        assertEquals(19, state.stopped.size)
        assertEquals("vllm-qwen3-6-27b-fp8", state.stopped.first().name) // host_port 3302, first stopped row
        assertEquals(false, state.stale)
    }

    @Test
    fun `an exited service in the initial load carries its exit code`() {
        server.enqueue(MockResponse.Builder().body(readFixture("services_list.json")).build())
        val viewModel = viewModel()

        viewModel.start()
        val state = settled(viewModel) as ModelsUiState.Loaded

        val crashed = state.stopped.first { it.name == "llamacpp-qwen3-5-397b-a17b-iq4xs" }
        assertEquals(137, crashed.exitCode)
        assertTrue(crashed.isExited)
    }

    @Test
    fun `a failing initial fetch is the Failed state, not a silent empty list`() {
        server.enqueue(MockResponse.Builder().code(503).body("""{"error": "Docker socket unavailable"}""").build())
        val viewModel = viewModel()

        viewModel.start()
        val state = settled(viewModel)

        assertTrue(state is ModelsUiState.Failed)
        assertEquals("Docker socket unavailable", (state as ModelsUiState.Failed).message)
    }

    /**
     * F10-R1's fifth criterion: the live services stream dropping is surfaced
     * as `stale = true` on the Models screen's own state, layered on top of
     * the initial REST load — [ServicesStreamRepositoryTest] already proves
     * the repository-level mechanism; this proves the ViewModel actually
     * wires it through rather than discarding the flag.
     */
    @Test
    fun `a dropped services stream marks the state stale without losing the last known list`() {
        server.enqueue(MockResponse.Builder().body("""{"services": [], "total": 0, "running": 0, "stopped": 0}""").build())
        val servicesStreamTransport = ScriptedSseTransport()
        servicesStreamTransport.script(
            ScriptedSseTransport.Leg(
                payloads = listOf(
                    """{"type":"snapshot","data":{"services":[
                        {"name":"llamacpp-a","status":"running","kind":"chat","host_port":3301,"favorite":false}
                    ],"total":1,"running":1,"stopped":0}}""",
                ),
                failWith = RuntimeException("connection reset"),
            ),
        )
        servicesStreamTransport.whenScriptRunsOut = { ScriptedSseTransport.Leg(park = true) }
        val viewModel = ModelsViewModel(
            servicesRepository = servicesRepository,
            servicesStreamRepository = ServicesStreamRepository(servicesStreamTransport),
            gpuStreamRepository = GpuStreamRepository(FakeSseTransport()),
        )

        viewModel.start()
        settled(viewModel)
        viewModel.startStreamsLikeTheScreenWould()

        // First the live snapshot lands (not stale), then the drop (stale).
        val stale = runBlocking {
            withTimeout(10_000) {
                viewModel.state.first { it is ModelsUiState.Loaded && it.stale }
            }
        } as ModelsUiState.Loaded
        assertEquals(listOf("llamacpp-a"), stale.running.map { it.name })
    }

    @Test
    fun `GPU frames flow through into the state's gpu field`() {
        server.enqueue(MockResponse.Builder().body("""{"services": [], "total": 0, "running": 0, "stopped": 0}""").build())
        val gpuStreamTransport = FakeSseTransport()
        gpuStreamTransport.payloads = listOf(
            """{"gpus": [{"index": 0, "name": "RTX PRO 6000", "memory": {"total": 97887, "used": 61440},
                "temperature": {"current": 71}, "utilization": {"gpu_percent": 84},
                "power": {"draw": 318.0, "limit": {"enforced": 300.0}}}]}""",
        )
        val viewModel = viewModel(gpuStreamTransport = gpuStreamTransport)

        viewModel.start()
        settled(viewModel)
        viewModel.startStreamsLikeTheScreenWould()

        val loaded = runBlocking {
            withTimeout(10_000) {
                viewModel.state.first { it is ModelsUiState.Loaded && it.gpu is GpuState.Available }
            }
        } as ModelsUiState.Loaded
        val gpu = (loaded.gpu as GpuState.Available).gpus.single()
        assertEquals(84, gpu.utilizationPercent)
        assertEquals(71, gpu.temperatureC)
    }
}
