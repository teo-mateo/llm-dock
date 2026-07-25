package com.hpz.llmdockchat.core.auth

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.SessionAuthenticator
import com.hpz.llmdockchat.testing.FakeCredentialStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class SessionManagerTest {

    private lateinit var server: MockWebServer
    private var serverUrl: BaseUrl = baseUrl("http://placeholder.invalid")
    private lateinit var manager: SessionManager
    private val tokenStore = FakeTokenStore()
    private val credentials = FakeCredentialStore()
    private val serverUrlStore = FakeServerUrlStore()
    private val sessionState = SessionState()

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        serverUrl = baseUrl(server.url("/").toString())
        serverUrlStore.set(serverUrl)
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(tokenStore, sessionState))
            .authenticator(SessionAuthenticator(tokenStore, sessionState) { null })
            .build()
        val authService = AuthService(
            ApiClient(client, serverUrlStore, ApiJson, Dispatchers.IO),
        )
        manager = SessionManager(
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
        )
    }

    @After
    fun tearDown() {
        server.close()
    }

    private val session = MockResponse.Builder()
        .body("""{"token": "totp-fresh", "expires_in": 28800}""")
        .build()

    @Test
    fun `a password sign-in keeps the credential so the session can renew itself`() = runBlocking {
        server.enqueue(session)

        val result = manager.signInWithPassword(serverUrl, "hunter2")

        assertTrue(result.isSuccess)
        assertEquals("totp-fresh", tokenStore.current())
        assertEquals(Credential.Password("hunter2"), credentials.current())
        assertFalse(sessionState.authenticationRequired.value)
    }

    @Test
    fun `a failed password sign-in stores nothing`() = runBlocking {
        server.enqueue(MockResponse.Builder().code(401).body("""{"error": "Invalid token"}""").build())

        val result = manager.signInWithPassword(serverUrl, "wrong")

        assertTrue(result.isFailure)
        assertNull(tokenStore.current())
        assertNull(credentials.current())
    }

    /**
     * F01-R6's last criterion: a TOTP sign-in has nothing storable, so the
     * session cannot renew itself and the user will be asked again.
     */
    @Test
    fun `a TOTP sign-in stores a token and no credential`() = runBlocking {
        server.enqueue(session)

        val result = manager.signInWithTotpCode(serverUrl, "419283")

        assertTrue(result.isSuccess)
        assertEquals("totp-fresh", tokenStore.current())
        assertNull(credentials.current())
    }

    @Test
    fun `signing in with a code after a password drops the stale password`() = runBlocking {
        server.enqueue(session)
        credentials.save(Credential.Password("hunter2"))

        manager.signInWithTotpCode(serverUrl, "419283")

        assertNull(credentials.current())
    }

    @Test
    fun `sign out clears both secrets and keeps the address`() {
        tokenStore.update("totp-live")
        credentials.save(Credential.Password("hunter2"))
        val address = serverUrlStore.current()

        manager.signOut()

        assertNull(tokenStore.current())
        assertNull(credentials.current())
        assertEquals(address, serverUrlStore.current())
        assertTrue(sessionState.authenticationRequired.value)
        assertNull("a deliberate sign-out has nothing to explain", sessionState.reason.value)
    }
}
