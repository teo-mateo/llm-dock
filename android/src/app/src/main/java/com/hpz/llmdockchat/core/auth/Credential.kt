package com.hpz.llmdockchat.core.auth

/**
 * A long-lived secret the app can exchange for a fresh session token without
 * asking the user anything (F01-R6).
 *
 * `toString` is overridden on every variant. A data class would print the
 * secret into any log line, stack trace or crash report that happens to
 * interpolate it, which F01-R5 forbids outright.
 */
sealed interface Credential {

    /**
     * The dashboard password — `DASHBOARD_TOKEN` from `dashboard/.env`. Posted
     * as a bearer to `/api/auth/session`, which hands back a session token.
     */
    class Password(val secret: String) : Credential {
        override fun toString(): String = "Credential.Password(secret=***)"
        override fun equals(other: Any?): Boolean = other is Password && other.secret == secret
        override fun hashCode(): Int = secret.hashCode()
    }

    companion object {
        private const val PASSWORD_TAG = "password"

        /**
         * Tagged so a second credential kind — a stored TOTP secret, say — can
         * be added without a migration for anything already on disk.
         */
        fun encode(credential: Credential): String = when (credential) {
            is Password -> "$PASSWORD_TAG:${credential.secret}"
        }

        fun decode(stored: String): Credential? {
            val separator = stored.indexOf(':')
            if (separator <= 0) return null
            val secret = stored.substring(separator + 1)
            if (secret.isEmpty()) return null
            return when (stored.substring(0, separator)) {
                PASSWORD_TAG -> Password(secret)
                else -> null
            }
        }
    }
}
