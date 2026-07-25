package com.hpz.llmdockchat.core.net

import kotlinx.coroutines.CancellationException

/**
 * Runs an API call and returns its failure as a value. The [AppError] is
 * reachable from the failure through [appError].
 */
suspend fun <T> apiCall(block: suspend () -> T): Result<T> = try {
    Result.success(block())
} catch (e: CancellationException) {
    throw e
} catch (e: ApiException) {
    Result.failure(e)
} catch (e: Throwable) {
    Result.failure(ApiException(e.appError))
}
