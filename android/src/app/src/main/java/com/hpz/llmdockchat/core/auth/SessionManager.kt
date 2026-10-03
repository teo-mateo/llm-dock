package com.hpz.llmdockchat.core.auth

import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.ServerUrlStore

/**
 * Signing in and signing out, in one place. Screens call this; nothing else
 * writes the token or the credential. Candidate login uses its explicit URL;
 * the active address and secrets change only after it succeeds.
 */
class SessionManager(
    private val serverUrlStore: ServerUrlStore,
    private val tokenStore: TokenStore,
    private val credentials: CredentialStore,
    private val sessionState: SessionState,
    private val authService: AuthService,
    private val reauthenticator: CredentialReauthenticator,
) {

    /**
     * F01-R4. The password is kept (encrypted) so the session can be renewed
     * without asking again — the trade-off F01-R5 spells out.
     */
    suspend fun signInWithPassword(server: BaseUrl, password: String): Result<Unit> {
        val credential = Credential.Password(password)
        return signIn(server, credential) { authService.signIn(credential, server) }
    }

    /**
     * F01-R3. Nothing is stored but the token: no endpoint this app may call
     * exposes the TOTP secret, so there is nothing to renew the session with
     * once it dies. The user is told so on the Connect screen.
     */
    suspend fun signInWithTotpCode(server: BaseUrl, code: String): Result<Unit> =
        signIn(server, null) { authService.signInWithTotpCode(code, server) }

    /** F01-R7. The address stays; the token and the credential do not. */
    fun signOut() {
        tokenStore.clear()
        credentials.clear()
        reauthenticator.reset()
        sessionState.signedOut()
    }

    private suspend fun signIn(
        server: BaseUrl,
        credential: Credential?,
        login: suspend () -> Result<String>,
    ): Result<Unit> {
        return login().map { token ->
            tokenStore.clear()
            credentials.clear()
            serverUrlStore.set(server)
            tokenStore.update(token, server)
            if (credential != null) credentials.save(credential, server)
            reauthenticator.reset()
            sessionState.authenticated()
        }
    }
}
