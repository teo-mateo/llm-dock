package com.hpz.llmdockchat.feature.connect

import com.hpz.llmdockchat.core.auth.AuthService
import com.hpz.llmdockchat.core.auth.Credential
import com.hpz.llmdockchat.core.auth.CredentialReauthenticator
import com.hpz.llmdockchat.core.auth.SessionManager
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.SessionAuthenticator
import com.hpz.llmdockchat.data.HealthRepository
import com.hpz.llmdockchat.data.ReachabilityRepository
import com.hpz.llmdockchat.testing.FakeCredentialStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
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
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

class ConnectViewModelTest {

    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    private lateinit var server: MockWebServer
    private lateinit var address: String
    private lateinit var viewModel: ConnectViewModel

    private val tokenStore = FakeTokenStore()
    private val credentials = FakeCredentialStore()
    private val serverUrlStore = FakeServerUrlStore()
    private val sessionState = SessionState()

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        address = server.url("/").toString().trimEnd('/')

        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(tokenStore, sessionState))
            .authenticator(SessionAuthenticator(tokenStore, sessionState) { null })
            .build()
        val api = ApiClient(client, serverUrlStore, ApiJson, Dispatchers.IO)
        val authService = AuthService(api)

        viewModel = ConnectViewModel(
            sessionManager = SessionManager(
                serverUrlStore = serverUrlStore,
                tokenStore = tokenStore,
                credentials = credentials,
                sessionState = sessionState,
                authService = authService,
                reauthenticator = CredentialReauthenticator(
                    credentials = credentials,
                    sessionState = sessionState,
                    exchange = { Result.failure(IllegalStateException("not used")) },
                ),
            ),
            reachability = ReachabilityRepository(HealthRepository(api)),
            serverUrlStore = serverUrlStore,
            sessionState = sessionState,
        )
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun settled(): ConnectUiState = runBlocking {
        withTimeout(10_000) { viewModel.state.first { !it.busy } }
    }

    private fun healthy() = MockResponse.Builder()
        .body("""{"status": "healthy", "version": "1.0.0", "docker_available": true}""")
        .build()

    private fun session() = MockResponse.Builder()
        .body("""{"token": "totp-fresh", "expires_in": 28800}""")
        .build()

    /** F01-R1: "rejected inline before any request is made". */
    @Test
    fun `a malformed address never reaches the network`() {
        viewModel.onAddressChange("http://")
        viewModel.onPasswordChange("hunter2")
        viewModel.submit()

        val state = settled()
        assertNotNull(state.addressError)
        assertEquals(0, server.requestCount)
        assertFalse(state.signedIn)
    }

    @Test
    fun `a valid password signs in`() {
        server.enqueue(healthy())
        server.enqueue(session())

        viewModel.onAddressChange(address)
        viewModel.onPasswordChange("hunter2")
        viewModel.submit()

        val state = settled()
        assertTrue(state.failure ?: "", state.signedIn)
        assertEquals("totp-fresh", tokenStore.current())
        assertEquals(Credential.Password("hunter2"), credentials.current())
        assertEquals("/api/health", server.takeRequest().url.encodedPath)
        assertEquals("/api/auth/session", server.takeRequest().url.encodedPath)
    }

    /**
     * F01-R2's whole purpose: separate "wrong address" from "wrong credential".
     * A host that answers but is not the dashboard must not consume a code.
     */
    @Test
    fun `a host that is not a dashboard is reported without attempting a login`() {
        server.enqueue(MockResponse.Builder().body("""{"error": {"message": "Invalid API Key"}}""").build())

        viewModel.onAddressChange(address)
        viewModel.onPasswordChange("hunter2")
        viewModel.submit()

        val state = settled()
        assertFalse(state.signedIn)
        assertTrue(state.failure.orEmpty(), state.failure!!.contains("not an llm-dock dashboard"))
        assertEquals(1, server.requestCount)
        assertNull(tokenStore.current())
    }

    /** F01-R3: the server's own message, the address untouched, ready to retry. */
    @Test
    fun `an invalid code shows the server's message and leaves the address alone`() {
        server.enqueue(healthy())
        server.enqueue(
            MockResponse.Builder().code(401).body("""{"error": "Invalid TOTP code"}""").build(),
        )

        viewModel.onAddressChange(address)
        viewModel.onMethodChange(LoginMethod.CODE)
        viewModel.onCodeChange("000000")

        val state = settled()
        assertEquals("Invalid TOTP code", state.failure)
        assertEquals(address, state.address)
        assertEquals("", state.code)
        assertFalse(state.signedIn)
        assertNull(credentials.current())
    }

    /** F01-R3: "submits without needing a separate button press once complete". */
    @Test
    fun `the sixth digit submits on its own`() {
        server.enqueue(healthy())
        server.enqueue(session())

        viewModel.onAddressChange(address)
        viewModel.onMethodChange(LoginMethod.CODE)
        "41928".forEachIndexed { index, _ -> viewModel.onCodeChange("41928".take(index + 1)) }
        assertEquals(0, server.requestCount)

        viewModel.onCodeChange("419283")

        assertTrue(settled().signedIn)
        assertEquals(2, server.requestCount)
        server.takeRequest()
        assertEquals("419283", server.takeRequest().headers[AuthService.TOTP_CODE_HEADER])
    }

    @Test
    fun `non-digits and overlong input never reach the field`() {
        viewModel.onCodeChange("4a1-9 2 8 3 7 7")
        assertEquals("419283", viewModel.state.value.code)
    }

    @Test
    fun `a saved address is prefilled`() {
        serverUrlStore.set(com.hpz.llmdockchat.testing.baseUrl("https://dock.example"))
        val fresh = ConnectViewModel(
            sessionManager = SessionManager(
                serverUrlStore, tokenStore, credentials, sessionState,
                AuthService(ApiClient(OkHttpClient(), serverUrlStore, ApiJson, Dispatchers.IO)),
                CredentialReauthenticator(credentials, sessionState) {
                    Result.failure(IllegalStateException("not used"))
                },
            ),
            reachability = ReachabilityRepository(
                HealthRepository(ApiClient(OkHttpClient(), serverUrlStore, ApiJson, Dispatchers.IO)),
            ),
            serverUrlStore = serverUrlStore,
            sessionState = sessionState,
        )
        assertEquals("https://dock.example", fresh.state.value.address)
    }
}
