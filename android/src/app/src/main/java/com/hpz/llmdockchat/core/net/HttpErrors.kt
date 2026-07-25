package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.error.ErrorBody

/**
 * Maps a non-2xx response onto an [AppError], preferring the dashboard's own
 * `{"error": "..."}` text over anything this client could invent (F00-R4).
 */
/**
 * [credentialRejected] flips the meaning of a 401. On an ordinary route it says
 * the session is gone, which is [AppError.Unauthenticated] and not something a
 * screen should render the server's words for. On a route that *establishes* a
 * session it says the password or code just supplied is wrong — and F01-R3 and
 * F01-R4 both require the dashboard's own message ("Invalid TOTP code") to
 * reach the user.
 */
fun httpError(status: Int, body: String?, credentialRejected: Boolean = false): AppError {
    if (status == 401 && !credentialRejected) return AppError.Unauthenticated
    val serverMessage = ErrorBody.extract(body)
    return AppError.Http(
        status = status,
        message = serverMessage ?: defaultMessage(status),
        fromServer = serverMessage != null,
    )
}

private fun defaultMessage(status: Int): String = when (status) {
    400 -> "The server rejected this request."
    401 -> "The server rejected that credential."
    403 -> "The server refused this request."
    404 -> "Not found on the server."
    409 -> "The server rejected this because something else is in progress."
    in 500..599 -> "The server failed to handle this request (HTTP $status)."
    else -> "The server returned HTTP $status."
}
