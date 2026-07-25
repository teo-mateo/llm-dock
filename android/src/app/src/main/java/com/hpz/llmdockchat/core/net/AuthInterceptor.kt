package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.auth.Reauthenticator
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.auth.TokenStore
import com.hpz.llmdockchat.core.error.AppError
import okhttp3.Interceptor
import okhttp3.Response

/**
 * Attaches `Authorization: Bearer <token>` to every request that needs one, and
 * adopts a rotated `X-TOTP-Token` when the dashboard issues one (F00-R2).
 *
 * With no token stored it mints one from the credential before sending
 * (F01-R6). That is not a nicety: a dashboard restart 401s the first request,
 * which discards the dead token, and every request queued behind it would
 * otherwise fail here with nothing stored — turning one expired session into a
 * trip to the Connect screen. The exchange is single-flight, so a request
 * arriving while one is already running waits for it rather than starting a
 * second.
 *
 * Only when there is nothing left to try is the request failed here rather than
 * sent, as F00-R2 requires.
 */
class AuthInterceptor(
    private val tokenStore: TokenStore,
    private val sessionState: SessionState,
    private val reauthenticator: Reauthenticator = Reauthenticator.NoCredential,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val outgoing = when {
            // The caller brought its own credential — /api/auth/session posts
            // the dashboard password as its bearer.
            request.header(AUTHORIZATION) != null -> request
            Endpoints.establishesSession(request) -> request
            else -> request.newBuilder().header(AUTHORIZATION, "Bearer ${bearer()}").build()
        }

        val response = chain.proceed(outgoing)
        response.header(TOTP_TOKEN_HEADER)?.takeIf { it.isNotBlank() }?.let(tokenStore::update)
        return response
    }

    private fun bearer(): String {
        tokenStore.current()?.takeIf { it.isNotBlank() }?.let { return it }

        val fresh = reauthenticator.reauthenticate()?.takeIf { it.isNotBlank() }
        if (fresh == null) {
            sessionState.requireAuthentication()
            throw ApiException(AppError.Unauthenticated)
        }
        tokenStore.update(fresh)
        return fresh
    }

    companion object {
        const val AUTHORIZATION = "Authorization"
        const val TOTP_TOKEN_HEADER = "X-TOTP-Token"
    }
}
