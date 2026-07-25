package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.error.AppError
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

/**
 * SSE over an authenticated OkHttp call — the reason a plain `EventSource`
 * cannot be used (F00-R6).
 *
 * The body is read line by line off a buffered source, so a frame split across
 * socket reads is reassembled before the parser ever sees it. [client] must be
 * configured with no read timeout; a quiet stream is normal.
 *
 * The reading runs as a child coroutine and the call is cancelled from
 * [awaitClose]. That indirection is load-bearing: a quiet stream parks the
 * reader inside a blocking socket read, which cannot observe coroutine
 * cancellation, so only cancelling the call unblocks it — and `awaitClose` runs
 * while the scope is being cancelled, rather than after it has completed.
 */
class OkHttpSseTransport(
    private val client: OkHttpClient,
    private val serverUrlStore: ServerUrlStore,
    private val ioDispatcher: CoroutineDispatcher,
) : SseTransport {

    override fun open(request: StreamRequest): Flow<String> = channelFlow {
        val base = serverUrlStore.current()
            ?: throw ApiException(AppError.Unexpected(IllegalStateException("No server configured.")))

        val httpRequest = Request.Builder()
            .url(base.resolve(request.path, request.query))
            .header("Accept", "text/event-stream")
            .header("Cache-Control", "no-cache")
            .method(request.method, request.body?.toRequestBody(JSON_MEDIA_TYPE))
            .build()

        val call = client.newCall(httpRequest)

        launch(ioDispatcher) {
            try {
                val response = try {
                    call.execute()
                } catch (e: ApiException) {
                    throw e
                } catch (e: IOException) {
                    throw ApiException(AppError.Network(e))
                }

                response.use { open ->
                    if (!open.isSuccessful) {
                        val body = runCatching { open.body.string() }.getOrNull()
                        throw ApiException(httpError(open.code, body))
                    }

                    val source = open.body.source()
                    val parser = SseFrameParser()
                    while (true) {
                        val line = try {
                            source.readUtf8Line()
                        } catch (e: IOException) {
                            if (call.isCanceled()) break
                            throw ApiException(AppError.Network(e))
                        } ?: break
                        parser.onLine(line)?.let { send(it) }
                    }
                }
                close()
            } catch (e: Throwable) {
                // A cancelled call is the collector going away, not a failure.
                close(if (call.isCanceled()) null else e)
            }
        }

        awaitClose { call.cancel() }
    }

    companion object {
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
    }
}
