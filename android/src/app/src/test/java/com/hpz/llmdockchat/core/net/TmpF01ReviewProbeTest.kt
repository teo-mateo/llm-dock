package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.auth.Credential
import com.hpz.llmdockchat.core.auth.CredentialReauthenticator
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.testing.FakeCredentialStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import mockwebserver3.Dispatcher
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
import okhttp3.OkHttpClient
import okhttp3.Request
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.atomic.AtomicInteger

/**
 * Review probe (F01). Left in place per WORK_INSTRUCTIONS.md; asserts only what
 * the implementation actually does today, so it will not flake.
 */
class TmpF01ReviewProbeTest {

    private lateinit var server: MockWebServer
    private val hits = AtomicInteger(0)

    @Before
    fun setUp() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                hits.incrementAndGet()
                return MockResponse.Builder().code(401).body("""{"error": "nope"}""").build()
            }
        }
        server.start()
    }

    @After
    fun tearDown() = server.close()

    /**
     * The pathological case: the credential exchange keeps succeeding but the
     * dashboard rejects every token it issues. Must terminate, not spin.
     */
    @Test
    fun `a server that 401s even a freshly minted token does not loop`() {
        val tokenStore = FakeTokenStore("totp-stale")
        val sessionState = SessionState()
        val exchanges = AtomicInteger(0)
        val reauthenticator = CredentialReauthenticator(
            credentials = FakeCredentialStore(Credential.Password("hunter2")),
            sessionState = sessionState,
        ) { Result.success("totp-fresh-${exchanges.incrementAndGet()}") }

        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(tokenStore, sessionState, reauthenticator))
            .authenticator(SessionAuthenticator(tokenStore, sessionState, reauthenticator))
            .build()

        val code = client.newCall(Request.Builder().url(server.url("/api/x")).build())
            .execute().use { it.code }

        assertEquals(401, code)
        assertTrue("requests should be bounded, got ${hits.get()}", hits.get() <= 4)
        assertTrue("exchanges should be bounded, got ${exchanges.get()}", exchanges.get() <= 2)
        assertTrue(sessionState.authenticationRequired.value)
    }

    /**
     * Documents a real rough edge rather than asserting it is correct: once a
     * rejected password has been discarded, the *next* 401 finds no credential
     * and overwrites the accurate "password was rejected" notice with the
     * TOTP-flavoured one, which a password user never chose.
     */
    @Test
    fun `a second 401 after a rejection replaces the reason with the TOTP wording`() {
        val sessionState = SessionState()
        val credentials = FakeCredentialStore(Credential.Password("hunter2"))
        val subject = CredentialReauthenticator(credentials, sessionState) {
            Result.failure(ApiException(AppError.Http(401, "Invalid token", true)))
        }

        subject.reauthenticate()
        assertEquals(CredentialReauthenticator.REJECTED, sessionState.reason.value)

        subject.reauthenticate()
        assertEquals(CredentialReauthenticator.NO_CREDENTIAL, sessionState.reason.value)
    }
}
