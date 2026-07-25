package com.hpz.llmdockchat.core.error

/**
 * Every failure the app can show. Screens render an [AppError]; they never
 * parse an error body themselves.
 */
sealed interface AppError {

    /**
     * A non-2xx response. [message] is always displayable; [fromServer]
     * distinguishes the dashboard's own `{"error": "..."}` text from a
     * message this client derived from the status code.
     */
    data class Http(
        val status: Int,
        val message: String,
        val fromServer: Boolean,
    ) : AppError

    /** No usable session token: either none stored, or the server rejected it. */
    data object Unauthenticated : AppError

    /** The request never completed — DNS, connect, TLS, socket. */
    data class Network(val cause: Throwable) : AppError

    /** A response arrived but did not decode into the expected shape. */
    data class Parse(val cause: Throwable) : AppError

    /** Anything else. */
    data class Unexpected(val cause: Throwable) : AppError
}

val AppError.displayMessage: String
    get() = when (this) {
        is AppError.Http -> message
        AppError.Unauthenticated -> "Sign in again to continue."
        is AppError.Network -> cause.message?.takeIf { it.isNotBlank() }
            ?.let { "Could not reach the server: $it" }
            ?: "Could not reach the server."
        is AppError.Parse -> "The server sent a response this app could not read."
        is AppError.Unexpected -> cause.message?.takeIf { it.isNotBlank() }
            ?: "Something went wrong."
    }
