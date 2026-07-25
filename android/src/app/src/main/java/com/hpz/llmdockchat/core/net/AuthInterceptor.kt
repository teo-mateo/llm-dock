package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.auth.TokenStore
import com.hpz.llmdockchat.core.error.AppError
import okhttp3.Interceptor
import okhttp3.Request
import okhttp3.Response

/**
 * Attaches `Authorization: Bearer <token>` to every request that needs one, and
 * adopts a rotated `X-TOTP-Token` when the dashboard issues one (F00-R2).
 *
 * With no token stored, the request is failed here rather than sent: an
 * unauthenticated call would only come back 401, and F00-R2 requires it never
 * reach the network.
 */
class AuthInterceptor(
    private val tokenStore: TokenStore,
    private val sessionState: SessionState,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val outgoing = when {
            // The caller brought its own credential — /api/auth/session posts
            // the dashboard password as its bearer.
            request.header(AUTHORIZATION) != null -> request
            Endpoints.establishesSession(request) -> request
            else -> {
                val token = tokenStore.current()
                if (token.isNullOrBlank()) {
                    sessionState.requireAuthentication()
                    throw ApiException(AppError.Unauthenticated)
                }
                request.newBuilder().header(AUTHORIZATION, "Bearer $token").build()
            }
        }

        val response = chain.proceed(outgoing)
        response.header(TOTP_TOKEN_HEADER)?.takeIf { it.isNotBlank() }?.let(tokenStore::update)
        return response
    }

    companion object {
        const val AUTHORIZATION = "Authorization"
        const val TOTP_TOKEN_HEADER = "X-TOTP-Token"
    }
}
