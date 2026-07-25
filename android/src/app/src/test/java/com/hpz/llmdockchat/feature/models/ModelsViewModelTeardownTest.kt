package com.hpz.llmdockchat.feature.models

import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.data.GpuStreamRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeSseTransport
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import com.hpz.llmdockchat.testing.quiesceAndRelease
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import java.util.concurrent.Executors

/**
 * F10-R3's third criterion: "closing the tab stops the stream". On device,
 * switching to the Chats tab was found to leave both SSE sockets `ESTAB` in
 * `ss -tnp` when the two live streams were launched from
 * `ModelsViewModel`'s own `viewModelScope` — Navigation Compose's tab-switch
 * idiom (`popUpTo(...) { saveState = true }` / `restoreState = true`, the same
 * one used for the Chats tab) keeps a Models-tab `ModelsViewModel` instance
 * cached across a switch, and anything running in its scope survives right
 * along with it. That is why [ModelsViewModel.observeServicesStream] /
 * [ModelsViewModel.observeGpuStream] hand back bare flows instead of
 * subscribing internally — the real owner of "does this stay connected" is
 * whoever calls `collect`, which in production is [ModelsScreen]'s own
 * `LaunchedEffect`s, torn down by Compose the moment the destination stops
 * being current.
 *
 * This test stands in for those `LaunchedEffect`s: it collects both flows
 * from jobs of its own, then cancels those jobs — not `store.clear()` — and
 * proves the parked transports were genuinely cancelled. Same
 * park-on-an-explicit-gate pattern as `ThreadReconnectTeardownTest` and
 * `GpuStreamRepositoryTest`'s own cancellation test.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ModelsViewModelTeardownTest {

    private lateinit var server: MockWebServer
    private lateinit var servicesRepository: ServicesRepository
    private lateinit var servicesStreamTransport: FakeSseTransport
    private lateinit var gpuStreamTransport: FakeSseTransport
    private val store = ViewModelStore()
    private val mainExecutor = Executors.newSingleThreadExecutor { Thread(it, "probe-main") }

    @Before
    fun setUp() {
        Dispatchers.setMain(mainExecutor.asCoroutineDispatcher())
        server = MockWebServer()
        server.start()
        val urlStore = FakeServerUrlStore(baseUrl(server.url("/").toString()))
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .build()
        servicesRepository = ServicesRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        servicesStreamTransport = FakeSseTransport().apply { stayOpen = true }
        gpuStreamTransport = FakeSseTransport().apply { stayOpen = true }
    }

    @After
    fun tearDown() {
        store.clear()
        server.close()
        mainExecutor.quiesceAndRelease()
        Dispatchers.resetMain()
    }

    private fun viewModel(): ModelsViewModel = ViewModelProvider.create(
        store,
        viewModelFactory {
            initializer {
                ModelsViewModel(
                    servicesRepository = servicesRepository,
                    servicesStreamRepository = ServicesStreamRepository(servicesStreamTransport),
                    gpuStreamRepository = GpuStreamRepository(gpuStreamTransport),
                )
            }
        },
    )[ModelsViewModel::class]

    @Test
    fun `cancelling the screen's stream collectors tears down both connections, and neither resubscribes`() = runBlocking {
        server.enqueue(MockResponse.Builder().body("""{"services": [], "total": 0, "running": 0, "stopped": 0}""").build())

        val viewModel = viewModel()
        viewModel.start()
        withTimeout(TIMEOUT_MS) { viewModel.state.first { it is ModelsUiState.Loaded } }

        // What ModelsScreen's two LaunchedEffects do — collect, and feed the
        // result back into the ViewModel.
        val servicesJob: Job = launch { viewModel.observeServicesStream().collect { viewModel.applyServicesUpdate(it) } }
        val gpuJob: Job = launch { viewModel.observeGpuStream().collect { viewModel.applyGpuUpdate(it) } }

        withTimeout(TIMEOUT_MS) { servicesStreamTransport.parked.await() }
        withTimeout(TIMEOUT_MS) { gpuStreamTransport.parked.await() }

        // What leaving the Models tab does to composition — deliberately NOT
        // store.clear(): the ViewModel is cached by Navigation Compose's
        // saveState/restoreState and survives this exactly as it does on device.
        servicesJob.cancel()
        gpuJob.cancel()

        withTimeout(TIMEOUT_MS) { servicesStreamTransport.cancelled.await() }
        withTimeout(TIMEOUT_MS) { gpuStreamTransport.cancelled.await() }

        delay(300)
        assertEquals("the services stream resubscribed after the screen went away", 1, servicesStreamTransport.requests.size)
        assertEquals("the GPU stream resubscribed after the screen went away", 1, gpuStreamTransport.requests.size)
    }

    /**
     * The regression this class exists to prevent, made explicit: a
     * [ModelsViewModel] that survives a tab switch (never cleared, no
     * collector ever attached) must not, on its own, hold either stream open.
     * `store.clear()` is deliberately never called here — the point is that
     * the ViewModel stays alive and idle, the same as while the Chats tab is
     * showing, yet nothing was ever subscribed.
     */
    @Test
    fun `the ViewModel surviving a tab switch does not by itself keep a stream connected`() = runBlocking {
        server.enqueue(MockResponse.Builder().body("""{"services": [], "total": 0, "running": 0, "stopped": 0}""").build())
        val viewModel = viewModel()
        viewModel.start()
        withTimeout(TIMEOUT_MS) { viewModel.state.first { it is ModelsUiState.Loaded } }

        delay(300)
        assertEquals("nothing subscribed, so nothing should have connected", 0, servicesStreamTransport.requests.size)
        assertEquals("nothing subscribed, so nothing should have connected", 0, gpuStreamTransport.requests.size)
    }

    private companion object {
        const val TIMEOUT_MS = 10_000L
    }
}
