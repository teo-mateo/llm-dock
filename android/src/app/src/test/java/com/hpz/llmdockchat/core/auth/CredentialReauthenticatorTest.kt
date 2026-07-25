package com.hpz.llmdockchat.core.auth

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.testing.FakeCredentialStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class CredentialReauthenticatorTest {

    private val parkedStates = setOf(
        Thread.State.WAITING,
        Thread.State.TIMED_WAITING,
        Thread.State.BLOCKED,
    )

    private val credentials = FakeCredentialStore(Credential.Password("hunter2"))
    private val sessionState = SessionState()

    private fun reauthenticator(
        maxConsecutiveFailures: Int = CredentialReauthenticator.DEFAULT_MAX_CONSECUTIVE_FAILURES,
        exchange: (Credential) -> Result<String>,
    ) = CredentialReauthenticator(
        credentials = credentials,
        sessionState = sessionState,
        maxConsecutiveFailures = maxConsecutiveFailures,
        exchange = exchange,
    )

    private fun rejected() =
        Result.failure<String>(ApiException(AppError.Http(401, "Invalid token", true)))

    @Test
    fun `the stored credential is exchanged for a fresh token`() {
        val exchanged = mutableListOf<Credential>()
        val token = reauthenticator { credential ->
            exchanged += credential
            Result.success("totp-fresh")
        }.reauthenticate()

        assertEquals("totp-fresh", token)
        assertEquals(listOf(Credential.Password("hunter2")), exchanged)
        assertFalse(sessionState.authenticationRequired.value)
    }

    /**
     * A dashboard restart invalidates every token at once, so every in-flight
     * request comes back 401 together. Each reaches OkHttp's `Authenticator` on
     * its own thread; without this, one dead session costs N sign-ins.
     */
    @Test
    fun `concurrent callers share one credential exchange`() {
        val followerCount = 11
        val exchanges = AtomicInteger(0)
        val exchangeEntered = CountDownLatch(1)
        val finish = CountDownLatch(1)

        val subject = reauthenticator {
            exchanges.incrementAndGet()
            exchangeEntered.countDown()
            check(finish.await(5, TimeUnit.SECONDS)) { "the test never released the exchange" }
            Result.success("totp-shared")
        }

        val tokens = arrayOfNulls<String>(followerCount + 1)
        val leader = Thread { tokens[0] = subject.reauthenticate() }.apply { start() }
        // The leader now owns the in-flight exchange and cannot leave it until
        // `finish`, so every follower below is guaranteed to join rather than
        // start its own.
        assertTrue(exchangeEntered.await(5, TimeUnit.SECONDS))

        val followers = (1..followerCount).map { index ->
            Thread { tokens[index] = subject.reauthenticate() }.apply { start() }
        }
        // Parked inside the shared future — no sleep, no timing assumption.
        awaitUntil("followers never parked") {
            followers.all { it.state in parkedStates }
        }

        finish.countDown()
        (followers + leader).forEach { it.join(5_000) }

        assertEquals(List(followerCount + 1) { "totp-shared" }, tokens.toList())
        assertEquals(1, exchanges.get())
    }

    private fun awaitUntil(what: String, condition: () -> Boolean) {
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5)
        while (System.nanoTime() < deadline) {
            if (condition()) return
            Thread.sleep(5)
        }
        throw AssertionError(what)
    }

    @Test
    fun `a later caller gets its own exchange once the first has finished`() {
        val exchanges = AtomicInteger(0)
        val subject = reauthenticator {
            Result.success("totp-${exchanges.incrementAndGet()}")
        }

        assertEquals("totp-1", subject.reauthenticate())
        assertEquals("totp-2", subject.reauthenticate())
    }

    /**
     * `/api/auth/session` answers 401 only when the credential itself is wrong,
     * so retrying can never succeed. Keeping it would mean one doomed exchange
     * per request for as long as the app runs.
     */
    @Test
    fun `a rejected credential is discarded and explained`() {
        val subject = reauthenticator { rejected() }

        assertNull(subject.reauthenticate())
        assertNull(credentials.current())
        assertTrue(sessionState.authenticationRequired.value)
        assertEquals(CredentialReauthenticator.REJECTED, sessionState.reason.value)
    }

    @Test
    fun `no stored credential says so rather than failing silently`() {
        credentials.clear()
        var attempts = 0
        val subject = reauthenticator { attempts++; Result.success("totp-never") }

        assertNull(subject.reauthenticate())
        assertEquals(0, attempts)
        assertEquals(CredentialReauthenticator.NO_CREDENTIAL, sessionState.reason.value)
    }

    @Test
    fun `repeated non-rejection failures stop after the bound`() {
        val attempts = AtomicInteger(0)
        val subject = reauthenticator(maxConsecutiveFailures = 3) {
            attempts.incrementAndGet()
            Result.failure(ApiException(AppError.Network(java.io.IOException("no route"))))
        }

        repeat(10) { assertNull(subject.reauthenticate()) }

        assertEquals(3, attempts.get())
        // A network failure is not the credential's fault, so it survives.
        assertEquals(Credential.Password("hunter2"), credentials.current())
    }

    @Test
    fun `a success clears the failure count`() {
        val attempts = AtomicInteger(0)
        var failing = true
        val subject = reauthenticator(maxConsecutiveFailures = 2) {
            attempts.incrementAndGet()
            if (failing) {
                Result.failure(ApiException(AppError.Network(java.io.IOException("no route"))))
            } else {
                Result.success("totp-ok")
            }
        }

        assertNull(subject.reauthenticate())
        failing = false
        assertEquals("totp-ok", subject.reauthenticate())
        failing = true
        assertNull(subject.reauthenticate())
        failing = false
        assertEquals("totp-ok", subject.reauthenticate())
        assertEquals(4, attempts.get())
    }

    @Test
    fun `reset lets a new sign-in try again after the bound was hit`() {
        var failing = true
        val subject = reauthenticator(maxConsecutiveFailures = 1) {
            if (failing) {
                Result.failure(ApiException(AppError.Network(java.io.IOException("no route"))))
            } else {
                Result.success("totp-ok")
            }
        }

        assertNull(subject.reauthenticate())
        failing = false
        assertNull("the bound is still in force", subject.reauthenticate())

        subject.reset()
        assertEquals("totp-ok", subject.reauthenticate())
    }
}
