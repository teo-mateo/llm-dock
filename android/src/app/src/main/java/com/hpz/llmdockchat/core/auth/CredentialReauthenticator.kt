package com.hpz.llmdockchat.core.auth

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.appError
import java.util.concurrent.ExecutionException
import java.util.concurrent.FutureTask
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/**
 * Silent re-authentication (F01-R6): exchanges the stored credential for a
 * fresh session token so the user only ever sees Connect after an explicit
 * sign-out or a credential the dashboard rejects.
 *
 * Two properties matter more than anything else here.
 *
 * **Single-flight.** A dashboard restart invalidates every token at once, so N
 * in-flight requests come back 401 together. Each one reaches OkHttp's
 * `Authenticator` on its own thread; without deduplication that is N credential
 * exchanges for one dead session. The first caller runs the exchange and the
 * rest wait on its result.
 *
 * **Bounded.** A credential the server rejects is cleared on the spot, and any
 * other repeated failure stops attempting after [maxConsecutiveFailures]. The
 * app falls back to Connect rather than exchanging a hopeless credential once
 * per request forever.
 *
 * Called from a network thread, so it blocks by design.
 */
class CredentialReauthenticator(
    private val credentials: CredentialStore,
    private val sessionState: SessionState,
    private val maxConsecutiveFailures: Int = DEFAULT_MAX_CONSECUTIVE_FAILURES,
    private val exchange: (Credential) -> Result<String>,
) : Reauthenticator {

    private val lock = ReentrantLock()
    private var inFlight: FutureTask<String?>? = null
    private val consecutiveFailures = AtomicInteger(0)

    /** Called when the user signs in, so a fresh credential starts from zero. */
    fun reset() {
        consecutiveFailures.set(0)
    }

    override fun reauthenticate(): String? {
        if (consecutiveFailures.get() >= maxConsecutiveFailures) return null

        var owner = false
        val task = lock.withLock {
            inFlight ?: FutureTask(::exchangeOnce).also {
                inFlight = it
                owner = true
            }
        }

        if (owner) {
            try {
                task.run()
            } finally {
                lock.withLock { inFlight = null }
            }
        }

        return try {
            task.get()
        } catch (e: ExecutionException) {
            consecutiveFailures.incrementAndGet()
            null
        } catch (e: InterruptedException) {
            Thread.currentThread().interrupt()
            null
        }
    }

    private fun exchangeOnce(): String? {
        // Nothing to exchange: a TOTP sign-in stores no credential, because no
        // endpoint this app may call hands out the secret. Say so plainly
        // rather than dropping the user on a bare Connect screen.
        val credential = credentials.current() ?: return refuse(NO_CREDENTIAL)

        val result = exchange(credential)
        result.getOrNull()?.takeIf { it.isNotBlank() }?.let { token ->
            consecutiveFailures.set(0)
            sessionState.authenticated()
            return token
        }

        // 401 from `/api/auth/session` means the password itself is wrong — the
        // dashboard's password changed, or it was mistyped and this is the
        // first request since. Retrying can never succeed, so drop it.
        if (result.exceptionOrNull()?.appError.isRejection()) {
            credentials.clear()
            return refuse(REJECTED)
        }

        consecutiveFailures.incrementAndGet()
        return null
    }

    private fun refuse(reason: String): String? {
        sessionState.requireAuthentication(reason)
        return null
    }

    private fun AppError?.isRejection(): Boolean = when (this) {
        AppError.Unauthenticated -> true
        // `/api/auth/session` answers 400 when the Authorization header is
        // missing and 401 when the credential is wrong, so a 4xx here is always
        // this client's fault and never worth repeating.
        is AppError.Http -> status in 400..499
        else -> false
    }

    companion object {
        const val DEFAULT_MAX_CONSECUTIVE_FAILURES = 3

        const val NO_CREDENTIAL =
            "Your session ended. Authenticator codes can't be saved, so enter a new one."
        const val REJECTED =
            "The dashboard rejected the saved password. Enter it again."
    }
}
