package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.error.ErrorBody

/**
 * Maps a non-2xx response onto an [AppError], preferring the dashboard's own
 * `{"error": "..."}` text over anything this client could invent (F00-R4).
 */
fun httpError(status: Int, body: String?): AppError {
    if (status == 401) return AppError.Unauthenticated
    val serverMessage = ErrorBody.extract(body)
    return AppError.Http(
        status = status,
        message = serverMessage ?: defaultMessage(status),
        fromServer = serverMessage != null,
    )
}

private fun defaultMessage(status: Int): String = when (status) {
    403 -> "The server refused this request."
    404 -> "Not found on the server."
    409 -> "The server rejected this because something else is in progress."
    in 500..599 -> "The server failed to handle this request (HTTP $status)."
    else -> "The server returned HTTP $status."
}
