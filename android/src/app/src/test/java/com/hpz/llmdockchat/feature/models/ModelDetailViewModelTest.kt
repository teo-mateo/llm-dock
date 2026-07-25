package com.hpz.llmdockchat.feature.models

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.MainDispatcherRule
import com.hpz.llmdockchat.testing.ScriptedSseTransport
import kotlinx.coroutines.DelicateCoroutinesApi
import kotlinx.coroutines.Dispatchers
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
 * F11-R1 (live status tracking a service that stops while the screen is
 * open) and F11-R2's fourth criterion (a 404 on the config fetch is a
 * partial view, not [ModelDetailUiState.Failed]).
 */
class ModelDetailViewModelTest {

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

    private fun viewModel(transport: ScriptedSseTransport = ScriptedSseTransport()) = ModelDetailViewModel(
        serviceName = "llamacpp-a",
        servicesRepository = servicesRepository,
        servicesStreamRepository = ServicesStreamRepository(transport),
    )

    private fun settled(viewModel: ModelDetailViewModel): ModelDetailUiState = runBlocking {
        withTimeout(10_000) { viewModel.state.first { it !is ModelDetailUiState.Loading } }
    }

    @OptIn(DelicateCoroutinesApi::class)
    private fun ModelDetailViewModel.startStreamLikeTheScreenWould() {
        GlobalScope.launch(Dispatchers.Main) { observeServicesStream().collect { applyLiveSummary(it) } }
    }

    private val serviceListBody = """
        {"services": [{"name": "llamacpp-a", "status": "running", "kind": "chat", "host_port": 3301, "favorite": false}],
         "total": 1, "running": 1, "stopped": 0}
    """.trimIndent()

    private val configBody = """
        {"service_name": "llamacpp-a", "config": {"model_path": "/models/a.gguf", "params": {"-ngl": "99", "-fa": "1"},
         "template_type": "llamacpp", "model_size_str": "26.1 GB", "api_key": "should-never-appear"}}
    """.trimIndent()

    @Test
    fun `loads the live summary and the config together`() {
        server.enqueue(MockResponse.Builder().body(serviceListBody).build())
        server.enqueue(MockResponse.Builder().body(configBody).build())

        val vm = viewModel()
        vm.start()
        val state = settled(vm) as ModelDetailUiState.Loaded

        assertEquals("llamacpp-a", state.summary.name)
        assertTrue(state.summary.isRunning)
        assertEquals(false, state.configMissing)
        assertEquals("/models/a.gguf", state.config?.modelPath)
        assertEquals(listOf("-ngl" to "99", "-fa" to "1"), state.config?.flags)
    }

    /** F11-R2: "api_key does not appear" — the mapper must never read it off
     * the wire in the first place, so there is no field on [state.config] to
     * assert is null; this proves the DTO's absence didn't just get lucky. */
    @Test
    fun `the config never carries an api key field to expose`() {
        server.enqueue(MockResponse.Builder().body(serviceListBody).build())
        server.enqueue(MockResponse.Builder().body(configBody).build())

        val vm = viewModel()
        vm.start()
        val state = settled(vm) as ModelDetailUiState.Loaded

        val fields = state.config!!.javaClass.declaredFields.map { it.name }
        assertTrue(fields.none { it.contains("api", ignoreCase = true) })
    }

    /**
     * Bug-shaped: a detail screen that treats any config-fetch failure as
     * fatal would show [ModelDetailUiState.Failed] for a container Docker
     * knows about but `services.json` doesn't — exactly the case F11-R2's
     * fourth criterion calls out as needing a graceful partial view. Confirms
     * the naive shape (any non-2xx -> Failed) is wrong by checking [Loaded]
     * comes back with [configMissing] set, not [Failed].
     */
    @Test
    fun `a 404 on the config fetch is a graceful partial view, not a Failed screen`() {
        server.enqueue(MockResponse.Builder().body(serviceListBody).build())
        server.enqueue(MockResponse.Builder().code(404).body("""{"error": "Service \"llamacpp-a\" not found"}""").build())

        val vm = viewModel()
        vm.start()
        val state = settled(vm)

        assertTrue(state is ModelDetailUiState.Loaded)
        val loaded = state as ModelDetailUiState.Loaded
        assertEquals(true, loaded.configMissing)
        assertEquals(null, loaded.config)
        assertEquals("llamacpp-a", loaded.summary.name)
    }

    @Test
    fun `a service absent from the list entirely is Failed, not a blank detail screen`() {
        server.enqueue(MockResponse.Builder().body("""{"services": [], "total": 0, "running": 0, "stopped": 0}""").build())

        val vm = viewModel()
        vm.start()
        val state = settled(vm)

        assertTrue(state is ModelDetailUiState.Failed)
    }

    /** F11-R1's first two criteria: status tracks the live stream, including a
     * stop that happens while the screen is already open. */
    @Test
    fun `a status change on the live stream updates the open detail screen in place`() {
        server.enqueue(MockResponse.Builder().body(serviceListBody).build())
        server.enqueue(MockResponse.Builder().body(configBody).build())
        val transport = ScriptedSseTransport()
        transport.script(
            ScriptedSseTransport.Leg(
                payloads = listOf(
                    """{"type":"snapshot","data":{"services":[
                        {"name":"llamacpp-a","status":"running","kind":"chat","host_port":3301,"favorite":false}
                    ],"total":1,"running":1,"stopped":0}}""",
                    """{"type":"delta","service_name":"llamacpp-a","status":"exited"}""",
                ),
                park = true,
            ),
        )
        val vm = viewModel(transport)
        vm.start()
        settled(vm)
        vm.startStreamLikeTheScreenWould()

        val stopped = runBlocking {
            withTimeout(10_000) {
                vm.state.first { it is ModelDetailUiState.Loaded && it.summary.isExited }
            }
        } as ModelDetailUiState.Loaded
        assertEquals("exited", stopped.summary.status)
    }
}
