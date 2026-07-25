package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.auth.Reauthenticator
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.auth.TokenStore
import okhttp3.Authenticator
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route

/**
 * A 401 is a normal event: the dashboard keeps sessions in process memory, so
 * a restart invalidates every token (F00-R3).
 *
 * Retrying is safe because `require_auth` returns 401 *before* invoking the
 * route, so nothing was created server-side by the rejected attempt
 * (Architecture D4).
 */
class SessionAuthenticator(
    private val tokenStore: TokenStore,
    private val sessionState: SessionState,
    private val reauthenticator: Reauthenticator,
) : Authenticator {

    override fun authenticate(route: Route?, response: Response): Request? {
        // A 401 from a login attempt means the credential is wrong. Re-running
        // the credential exchange here would loop through it a second time and
        // report the failure from the wrong place.
        if (Endpoints.establishesSession(response.request)) return null

        val attempted = response.request.header(AuthInterceptor.AUTHORIZATION)?.removePrefix("Bearer ")
        if (attempted != null && attempted == tokenStore.current()) {
            tokenStore.clear()
        }

        if (priorResponses(response) > 1) return giveUp()

        val fresh = reauthenticator.reauthenticate()?.takeIf { it.isNotBlank() } ?: return giveUp()

        tokenStore.update(fresh)
        sessionState.authenticated()
        return response.request.newBuilder()
            .header(AuthInterceptor.AUTHORIZATION, "Bearer $fresh")
            .build()
    }

    private fun giveUp(): Request? {
        sessionState.requireAuthentication()
        return null
    }

    private fun priorResponses(response: Response): Int {
        var count = 1
        var prior = response.priorResponse
        while (prior != null) {
            count++
            prior = prior.priorResponse
        }
        return count
    }
}
