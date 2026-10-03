package com.hpz.llmdockchat.core.auth

/**
 * Exchanges the stored credential for a fresh session token, or returns null
 * when there is no credential to exchange.
 *
 * Called from OkHttp's `Authenticator` on a network thread, so it blocks.
 * The initial build ships [NoCredential]; sign-in supplies the real
  * implementation by setting [ReauthenticatorHolder.delegate].
 */
fun interface Reauthenticator {
    fun reauthenticate(): String?

    companion object {
        val NoCredential = Reauthenticator { null }
    }
}

/**
 * Indirection so the OkHttp client can be built before a credential source
 * exists. Without it, sign-in would have to rebuild the HTTP stack.
 */
class ReauthenticatorHolder(
    @Volatile var delegate: Reauthenticator = Reauthenticator.NoCredential,
) : Reauthenticator {
    override fun reauthenticate(): String? = delegate.reauthenticate()
}
