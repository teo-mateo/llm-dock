package com.hpz.llmdockchat.feature.models

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.MainDispatcherRule
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
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
 * F11-R3/R4/F10-R5's confirm-then-act flow: naming the service, one at a
 * time, surfacing a failure without pretending success. Uses a real
 * [MockWebServer] round trip (like [com.hpz.llmdockchat.feature.models.ModelsViewModelTest]) rather than
 * a fake repository, so a bug in [ServicesRepository]'s own start/stop
 * wiring would show up here too.
 */
class ServiceControlControllerTest {

    // Main is set unconfined (F11-R4's own reasoning, MainDispatcherRule's
    // doc): `scope.launch { ... }` in ServiceControlController runs eagerly
    // up to its first real suspension, which is the `withContext(Dispatchers.IO)`
    // inside ApiClient — a genuine dispatcher hop, not a race. So the state
    // is already `InFlight` the instant `confirm()` returns, deterministically.
    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    private lateinit var server: MockWebServer
    private lateinit var repository: ServicesRepository
    private lateinit var scope: CoroutineScope

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
        repository = ServicesRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
        scope = CoroutineScope(Dispatchers.Main + Job())
    }

    @After
    fun tearDown() {
        scope.cancel()
        server.close()
    }

    private fun settled(controller: ServiceControlController) = runBlocking {
        withTimeout(10_000) { controller.actionState.first { it !is ServiceActionState.InFlight } }
    }

    /**
     * Bug-shaped: a naive controller that calls the repository straight from
     * `requestStop` (no confirm step at all) would stop the container the
     * instant the row's Stop button is tapped — exactly what F11-R3 forbids.
     * This asserts the state stays `Confirming` and nothing hit the wire.
     */
    @Test
    fun `requesting stop only opens the confirm dialog, it does not call stop yet`() {
        val controller = ServiceControlController(repository, scope)

        controller.requestStop("llamacpp-a")

        assertEquals(ServiceActionState.Confirming("llamacpp-a", ServiceAction.STOP), controller.actionState.value)
        assertEquals(0, server.requestCount)
    }

    @Test
    fun `confirming sends the stop request and returns to idle on success`() {
        server.enqueue(MockResponse.Builder().body("""{"success": true}""").build())
        val controller = ServiceControlController(repository, scope)
        controller.requestStop("llamacpp-a")

        controller.confirm()
        val state = settled(controller)

        assertEquals(ServiceActionState.Idle, state)
        val request = server.takeRequest()
        assertEquals("/api/services/llamacpp-a/stop", request.url.encodedPath)
        assertEquals("POST", request.method)
    }

    @Test
    fun `a failed start surfaces the server's error and does not claim success`() {
        server.enqueue(MockResponse.Builder().code(400).body("""{"error": "CUDA out of memory"}""").build())
        val controller = ServiceControlController(repository, scope)
        controller.requestStart("vllm-big")

        controller.confirm()
        val state = settled(controller)

        assertTrue(state is ServiceActionState.Failed)
        assertEquals("CUDA out of memory", (state as ServiceActionState.Failed).message)
        assertEquals(ServiceAction.START, state.action)
    }

    /**
     * F11-R4's third criterion: "cannot be double-fired". `confirm()` runs
     * eagerly up to the real dispatcher hop (see the class doc), so by the
     * time it returns the service is genuinely mid-request — a second
     * `requestStart` right then must be refused, not queued for after.
     */
    @Test
    fun `a second request is refused while one is already in flight`() {
        server.enqueue(MockResponse.Builder().body("""{"success": true}""").build())
        val controller = ServiceControlController(repository, scope)
        controller.requestStop("llamacpp-a")
        controller.confirm()

        assertEquals(ServiceActionState.InFlight("llamacpp-a", ServiceAction.STOP), controller.actionState.value)
        controller.requestStart("llamacpp-b")
        assertEquals(ServiceActionState.InFlight("llamacpp-a", ServiceAction.STOP), controller.actionState.value)

        settled(controller) // drain, so the server socket isn't left mid-response for tearDown
    }

    @Test
    fun `dismiss returns to idle without ever calling the server`() {
        val controller = ServiceControlController(repository, scope)
        controller.requestStart("llamacpp-a")

        controller.dismiss()

        assertEquals(ServiceActionState.Idle, controller.actionState.value)
        assertEquals(0, server.requestCount)
    }

    @Test
    fun `isInFlight is true only for the service actually being acted on`() {
        server.enqueue(MockResponse.Builder().body("""{"success": true}""").build())
        val controller = ServiceControlController(repository, scope)
        controller.requestStop("llamacpp-a")

        controller.confirm()

        assertTrue(controller.isInFlight("llamacpp-a"))
        assertTrue(!controller.isInFlight("llamacpp-b"))
        settled(controller)
    }
}
