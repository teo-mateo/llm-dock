package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.core.error.AppError
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.withContext
import kotlinx.serialization.DeserializationStrategy
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

/**
 * One-shot JSON calls. Resolves the base URL per request, so changing the
 * server address takes effect without restarting the app or rebuilding the
 * HTTP stack (F00-R1).
 *
 * Throws [ApiException]; callers that want a value-typed failure use
 * [apiCall].
 */
class ApiClient(
    private val client: OkHttpClient,
    private val serverUrlStore: ServerUrlStore,
    private val json: Json,
    private val ioDispatcher: CoroutineDispatcher,
) {

    suspend fun <T> get(
        path: String,
        deserializer: DeserializationStrategy<T>,
        query: Map<String, String> = emptyMap(),
    ): T = request("GET", path, deserializer, query)

    suspend fun <T> request(
        method: String,
        path: String,
        deserializer: DeserializationStrategy<T>,
        query: Map<String, String> = emptyMap(),
        body: String? = null,
    ): T = withContext(ioDispatcher) {
        val base = serverUrlStore.current()
            ?: throw ApiException(AppError.Unexpected(IllegalStateException("No server configured.")))

        val httpRequest = Request.Builder()
            .url(base.resolve(path, query))
            .method(method, body?.toRequestBody(JSON_MEDIA_TYPE))
            .build()

        val response = try {
            client.newCall(httpRequest).execute()
        } catch (e: ApiException) {
            throw e
        } catch (e: IOException) {
            throw ApiException(AppError.Network(e))
        }

        response.use {
            val text = runCatching { it.body.string() }.getOrNull()
            if (!it.isSuccessful) throw ApiException(httpError(it.code, text))
            try {
                json.decodeFromString(deserializer, text.orEmpty())
            } catch (e: Exception) {
                throw ApiException(AppError.Parse(e))
            }
        }
    }

    companion object {
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
    }
}
