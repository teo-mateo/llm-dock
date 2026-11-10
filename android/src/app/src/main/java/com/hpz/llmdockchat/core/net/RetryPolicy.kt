package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.error.AppError

/**
 * Whether a failed request is worth repeating.
 *
 * A network failure, a request timeout, a rate limit and a server failure are
 * all "not yet". A client error, an unreadable body or a rejected session will
 * answer the same way however many times it is asked, so retrying one only
 * keeps the caller busy against a result that cannot change.
 */
fun AppError.isTransient(): Boolean = when (this) {
    is AppError.Network -> true
    is AppError.Http -> status == 408 || status == 429 || status in 500..599
    AppError.Unauthenticated, is AppError.Parse, is AppError.Unexpected -> false
}
