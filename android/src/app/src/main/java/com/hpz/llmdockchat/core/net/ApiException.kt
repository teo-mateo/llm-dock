package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.error.displayMessage
import java.io.IOException

/**
 * Carries an [AppError] through OkHttp, which only propagates [IOException]
 * out of an interceptor or a call.
 */
class ApiException(val error: AppError) : IOException(error.displayMessage)

val Throwable.appError: AppError
    get() = when (this) {
        is ApiException -> error
        is IOException -> AppError.Network(this)
        else -> AppError.Unexpected(this)
    }
