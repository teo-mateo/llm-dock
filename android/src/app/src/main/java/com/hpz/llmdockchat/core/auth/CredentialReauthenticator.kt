package com.hpz.llmdockchat.core.auth

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.ServerUrlStore
import java.util.concurrent.ExecutionException
import java.util.concurrent.FutureTask
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/**
 * Silent re-authentication: exchanges the stored credential for a
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
    private val serverUrlStore: ServerUrlStore? = null,
    private val exchange: (Credential, BaseUrl?) -> Result<String>,
) : Reauthenticator {

    private val lock = ReentrantLock()
    private var inFlight: Pair<BaseUrl?, FutureTask<String?>>? = null
    private val consecutiveFailures = AtomicInteger(0)

    /** Called when the user signs in, so a fresh credential starts from zero. */
    fun reset() {
        consecutiveFailures.set(0)
    }

    override fun reauthenticate(): String? = reauthenticate(serverUrlStore?.current())

    override fun reauthenticate(server: BaseUrl?): String? {
        if (consecutiveFailures.get() >= maxConsecutiveFailures) return null
        if (!isCurrent(server)) return null

        var owner = false
        val task = lock.withLock {
            inFlight?.takeIf { it.first == server }?.second
                ?: FutureTask { exchangeOnce(server) }.also {
                    inFlight = server to it
                    owner = true
                }
        }

        if (owner) {
            try {
                task.run()
            } finally {
                lock.withLock { if (inFlight?.second === task) inFlight = null }
            }
        }

        return try {
            task.get()?.takeIf { isCurrent(server) }
        } catch (e: ExecutionException) {
            if (isCurrent(server)) consecutiveFailures.incrementAndGet()
            null
        } catch (e: InterruptedException) {
            Thread.currentThread().interrupt()
            null
        }
    }

    private fun exchangeOnce(server: BaseUrl?): String? {
        if (!isCurrent(server)) return null
        // Nothing to exchange: a TOTP sign-in stores no credential, because no
        // endpoint this app may call hands out the secret. Say so plainly
        // rather than dropping the user on a bare Connect screen.
        val credential = credentials.current(server) ?: return refuse(NO_CREDENTIAL, server)

        val result = exchange(credential, server)
        if (!isCurrent(server)) return null
        result.getOrNull()?.takeIf { it.isNotBlank() }?.let { token ->
            return if (withCurrent(server) {
                consecutiveFailures.set(0)
                sessionState.authenticated()
            }) token else null
        }

        // 401 from `/api/auth/session` means the password itself is wrong — the
        // dashboard's password changed, or it was mistyped and this is the
        // first request since. Retrying can never succeed, so drop it.
        if (result.exceptionOrNull()?.appError.isRejection()) {
            credentials.clear(server)
            return refuse(REJECTED, server)
        }

        withCurrent(server) { consecutiveFailures.incrementAndGet() }
        return null
    }

    private fun refuse(reason: String, server: BaseUrl?): String? {
        withCurrent(server) { sessionState.requireAuthentication(reason) }
        return null
    }

    private fun withCurrent(server: BaseUrl?, action: () -> Unit): Boolean = when {
        serverUrlStore == null -> { action(); true }
        server == null -> false
        else -> serverUrlStore.ifCurrent(server, action)
    }

    private fun isCurrent(server: BaseUrl?): Boolean =
        serverUrlStore == null || (server != null && serverUrlStore.current() == server)

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
