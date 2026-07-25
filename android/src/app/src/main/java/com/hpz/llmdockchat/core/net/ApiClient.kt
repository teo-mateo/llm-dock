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

    /**
     * [headers] is how the login routes carry their own credential —
     * `X-TOTP-Code`, or the password as an `Authorization` bearer. The
     * interceptor leaves a request that already has an `Authorization` header
     * alone, so a caller-supplied one is never overwritten (F00-R2).
     */
    suspend fun <T> request(
        method: String,
        path: String,
        deserializer: DeserializationStrategy<T>,
        query: Map<String, String> = emptyMap(),
        body: String? = null,
        headers: Map<String, String> = emptyMap(),
    ): T = withContext(ioDispatcher) {
        val base = serverUrlStore.current()
            ?: throw ApiException(AppError.Unexpected(IllegalStateException("No server configured.")))

        // OkHttp rejects a POST/PUT/PATCH with no body, and both login routes
        // send none — the credential is entirely in the headers.
        val requestBody = when {
            body != null -> body.toRequestBody(JSON_MEDIA_TYPE)
            method in METHODS_REQUIRING_A_BODY -> EMPTY_BODY
            else -> null
        }

        val httpRequest = Request.Builder()
            .url(base.resolve(path, query))
            .apply { headers.forEach { (name, value) -> header(name, value) } }
            .method(method, requestBody)
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
            if (!it.isSuccessful) {
                throw ApiException(
                    httpError(
                        status = it.code,
                        body = text,
                        credentialRejected = Endpoints.establishesSession(httpRequest),
                    ),
                )
            }
            try {
                json.decodeFromString(deserializer, text.orEmpty())
            } catch (e: Exception) {
                throw ApiException(AppError.Parse(e))
            }
        }
    }

    companion object {
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
        private val METHODS_REQUIRING_A_BODY = setOf("POST", "PUT", "PATCH")
        private val EMPTY_BODY = ByteArray(0).toRequestBody(null)
    }
}
