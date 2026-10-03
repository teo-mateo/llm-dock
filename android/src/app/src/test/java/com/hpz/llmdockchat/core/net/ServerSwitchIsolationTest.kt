package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.auth.AuthService
import com.hpz.llmdockchat.core.auth.CredentialReauthenticator
import com.hpz.llmdockchat.core.auth.ReauthenticatorHolder
import com.hpz.llmdockchat.core.auth.SessionManager
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.testing.FakeCredentialStore
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonElement
import mockwebserver3.Dispatcher
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class ServerSwitchIsolationTest {
    private lateinit var serverA: MockWebServer
    private lateinit var serverB: MockWebServer
    private val address = FakeServerUrlStore()
    private val tokens = FakeTokenStore()
    private val credentials = FakeCredentialStore()
    private val sessionState = SessionState()
    private val oldRequestEntered = CountDownLatch(1)
    private val releaseOldRequest = CountDownLatch(1)
    private val aLogins = AtomicInteger(0)
    private var blockOldRequests = true
    private var blockRenewal = false
    private val renewalEntered = CountDownLatch(1)
    private val releaseRenewal = CountDownLatch(1)

    @Before
    fun setUp() {
        serverA = MockWebServer()
        serverA.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse = when (request.url.encodedPath) {
                Endpoints.AUTH_SESSION -> {
                    val attempt = aLogins.incrementAndGet()
                    if (attempt > 1 && blockRenewal) {
                        renewalEntered.countDown()
                        check(releaseRenewal.await(10, TimeUnit.SECONDS))
                    }
                    session(if (attempt == 1) "totp-SERVER-A" else "totp-RENEWED-A")
                }
                Endpoints.SERVICES -> {
                    if (request.headers["Authorization"] == "Bearer totp-RENEWED-A") {
                        MockResponse.Builder().body("{}").build()
                    } else {
                        if (blockOldRequests) {
                            oldRequestEntered.countDown()
                            check(releaseOldRequest.await(10, TimeUnit.SECONDS))
                        }
                        MockResponse.Builder().code(401).body("""{"error":"expired"}""").build()
                    }
                }
                else -> MockResponse.Builder().code(404).build()
            }
        }
        serverA.start()
        serverB = MockWebServer()
        serverB.start()
    }

    @After
    fun tearDown() {
        releaseOldRequest.countDown()
        releaseRenewal.countDown()
        serverA.close()
        serverB.close()
    }

    private fun session(token: String) = MockResponse.Builder()
        .body("""{"token":"$token","expires_in":28800}""")
        .build()

    private fun stack(): Pair<SessionManager, ApiClient> {
        val holder = ReauthenticatorHolder()
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(tokens, sessionState, holder, address))
            .authenticator(SessionAuthenticator(tokens, sessionState, holder, address))
            .build()
        val api = ApiClient(client, address, ApiJson, Dispatchers.IO)
        val auth = AuthService(api)
        val renew = CredentialReauthenticator(
            credentials = credentials,
            sessionState = sessionState,
            serverUrlStore = address,
            exchange = { credential, server -> runBlocking { auth.signIn(credential, checkNotNull(server)) } },
        )
        holder.delegate = renew
        return SessionManager(address, tokens, credentials, sessionState, auth, renew) to api
    }

    @Test
    fun `failed B login cannot send A token or saved password to B`() = runBlocking {
        serverB.enqueue(MockResponse.Builder().code(401).body("""{"error":"bad password"}""").build())
        val (manager, api) = stack()
        val a = baseUrl(serverA.url("/").toString())
        val b = baseUrl(serverB.url("/").toString())

        assertTrue(manager.signInWithPassword(a, "SERVER_A_PASSWORD").isSuccess)
        assertTrue(manager.signInWithPassword(b, "B_INPUT_PASSWORD").isFailure)
        assertEquals(a, address.current())
        assertEquals("totp-SERVER-A", tokens.current())

        assertTrue(runCatching {
            api.get(Endpoints.SERVICES, JsonElement.serializer(), server = b)
        }.isFailure)
        assertEquals(1, serverB.requestCount)
        assertEquals("Bearer B_INPUT_PASSWORD", serverB.takeRequest().headers["Authorization"])
    }

    @Test
    fun `late A rejection cannot renew or replace B session`() = runBlocking {
        serverB.enqueue(session("totp-SERVER-B"))
        serverB.enqueue(MockResponse.Builder().body("{}").build())
        val (manager, api) = stack()
        val a = baseUrl(serverA.url("/").toString())
        val b = baseUrl(serverB.url("/").toString())
        assertTrue(manager.signInWithPassword(a, "SERVER_A_PASSWORD").isSuccess)

        val oldRequest = Thread {
            runBlocking {
                runCatching { api.get(Endpoints.SERVICES, JsonElement.serializer(), server = a) }
            }
        }
        oldRequest.start()
        assertTrue(oldRequestEntered.await(10, TimeUnit.SECONDS))

        assertTrue(manager.signInWithPassword(b, "SERVER_B_PASSWORD").isSuccess)
        releaseOldRequest.countDown()
        oldRequest.join(10_000)
        assertFalse(oldRequest.isAlive)
        assertEquals(b, address.current())
        assertEquals("totp-SERVER-B", tokens.current())

        api.get(Endpoints.SERVICES, JsonElement.serializer(), server = b)
        assertEquals(2, serverB.requestCount)
        assertEquals("Bearer SERVER_B_PASSWORD", serverB.takeRequest().headers["Authorization"])
        assertEquals("Bearer totp-SERVER-B", serverB.takeRequest().headers["Authorization"])
        assertEquals(2, serverA.requestCount)
    }

    @Test
    fun `the same server still renews a rejected session`() = runBlocking {
        blockOldRequests = false
        val (manager, api) = stack()
        val a = baseUrl(serverA.url("/").toString())
        assertTrue(manager.signInWithPassword(a, "SERVER_A_PASSWORD").isSuccess)

        api.get(Endpoints.SERVICES, JsonElement.serializer(), server = a)

        assertEquals(2, aLogins.get())
        assertEquals("totp-RENEWED-A", tokens.current())
        assertEquals(4, serverA.requestCount)
    }

    @Test
    fun `a renewal finishing after the switch cannot replace B token`() = runBlocking {
        blockOldRequests = false
        blockRenewal = true
        serverB.enqueue(session("totp-SERVER-B"))
        val (manager, api) = stack()
        val a = baseUrl(serverA.url("/").toString())
        val b = baseUrl(serverB.url("/").toString())
        assertTrue(manager.signInWithPassword(a, "SERVER_A_PASSWORD").isSuccess)

        val oldRequest = Thread {
            runBlocking { runCatching { api.get(Endpoints.SERVICES, JsonElement.serializer(), server = a) } }
        }
        oldRequest.start()
        assertTrue(renewalEntered.await(10, TimeUnit.SECONDS))

        assertTrue(manager.signInWithPassword(b, "SERVER_B_PASSWORD").isSuccess)
        releaseRenewal.countDown()
        oldRequest.join(10_000)
        assertFalse(oldRequest.isAlive)
        assertEquals(b, address.current())
        assertEquals("totp-SERVER-B", tokens.current())
        assertFalse(sessionState.authenticationRequired.value)
        assertEquals(1, serverB.requestCount)
        assertEquals("Bearer SERVER_B_PASSWORD", serverB.takeRequest().headers["Authorization"])
    }
}
