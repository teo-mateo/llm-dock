package com.hpz.llmdockchat.feature.thread

import com.hpz.llmdockchat.core.error.AppError

/**
 * Whether EOF reconciliation should ask the server again.
 *
 * A terminal failure ends the turn with an error: retrying a 404 or a response
 * this app cannot parse only keeps the UI reconnecting against a server that
 * will answer the same way forever. 5xx and 429 stay transient — a restarting
 * dashboard and a rate limit are both "not yet".
 */
internal fun AppError.isTransientForReconcile(): Boolean = when (this) {
    is AppError.Network -> true
    is AppError.Http -> status == 429 || status in 500..599
    AppError.Unauthenticated, is AppError.Parse, is AppError.Unexpected -> false
}
