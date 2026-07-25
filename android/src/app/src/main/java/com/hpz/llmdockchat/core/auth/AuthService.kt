package com.hpz.llmdockchat.core.auth

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.apiCall
import com.hpz.llmdockchat.data.dto.SessionDto
import com.hpz.llmdockchat.data.dto.TokenVerificationDto

/**
 * The two ways into the dashboard, and the token-liveness probe.
 *
 * Neither login route is decorated with `require_auth` server-side
 * (`dashboard/routes/system.py`), so neither may carry a session bearer:
 * `/api/auth/login` authenticates with `X-TOTP-Code`, and `/api/auth/session`
 * uses the password itself as the bearer. `Endpoints.establishesSession`
 * exempts both from the transport's token handling; this class must not
 * reintroduce one.
 */
class AuthService(private val api: ApiClient) {

    /** `POST /api/auth/session` with the dashboard password as the bearer (F01-R4). */
    suspend fun signIn(credential: Credential): Result<String> = when (credential) {
        is Credential.Password -> token(
            path = Endpoints.AUTH_SESSION,
            headers = mapOf("Authorization" to "Bearer ${credential.secret}"),
        )
    }

    /**
     * `POST /api/auth/login` with the six-digit code as `X-TOTP-Code` (F01-R3).
     *
     * Never sent on any other route: an expired `totp-` bearer makes
     * `require_auth` return 401 before it reaches the `X-TOTP-Code` branch
     * (`dashboard/auth.py:53-66`), so the code would be silently discarded.
     */
    suspend fun signInWithTotpCode(code: String): Result<String> = token(
        path = Endpoints.AUTH_LOGIN,
        headers = mapOf(TOTP_CODE_HEADER to code),
    )

    /** `POST /api/auth/verify` — authenticated, so it exercises the stored token. */
    suspend fun verify(): Result<Boolean> = apiCall {
        api.request(
            method = "POST",
            path = Endpoints.AUTH_VERIFY,
            deserializer = TokenVerificationDto.serializer(),
        ).valid
    }

    private suspend fun token(path: String, headers: Map<String, String>): Result<String> = apiCall {
        val session = api.request(
            method = "POST",
            path = path,
            deserializer = SessionDto.serializer(),
            headers = headers,
        )
        if (session.token.isBlank()) {
            throw ApiException(
                AppError.Http(
                    status = 200,
                    message = "The server accepted the sign-in but returned no session token.",
                    fromServer = false,
                ),
            )
        }
        session.token
    }

    companion object {
        const val TOTP_CODE_HEADER = "X-TOTP-Code"
    }
}
