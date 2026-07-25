package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.core.net.apiCall
import com.hpz.llmdockchat.data.dto.ServiceActionResponseDto
import com.hpz.llmdockchat.data.dto.ServiceDetailResponseDto
import com.hpz.llmdockchat.data.dto.ServiceListResponseDto
import com.hpz.llmdockchat.data.dto.ServiceLogsResponseDto
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.ServiceConfig
import com.hpz.llmdockchat.data.model.ServiceSummary
import kotlinx.coroutines.CancellationException

/**
 * `GET /api/services` (F03's model picker, later F10's models list). Returns
 * every compose service unfiltered — including non-chat and non-model
 * containers like `open-webui` — so each caller applies its own filter
 * ([ServiceSummary.isChatCapable] for F03) rather than this repository
 * guessing what a future feature needs.
 */
class ServicesRepository(private val api: ApiClient) {
    suspend fun list(): Result<List<ServiceSummary>> = apiCall {
        api.get(Endpoints.SERVICES, ServiceListResponseDto.serializer()).services.map { it.toDomain() }
    }

    /**
     * `GET /api/services/<name>` (F11-R2). A 404 is not a failure here — it
     * means Docker knows the container but `services.json` doesn't, F11-R2's
     * fourth criterion — so it comes back as `Result.success(null)` rather
     * than an error the detail screen would otherwise have to special-case
     * out of a [Result.failure].
     */
    suspend fun detail(name: String): Result<ServiceConfig?> = try {
        Result.success(
            api.get(Endpoints.serviceDetail(name), ServiceDetailResponseDto.serializer()).config.toDomain(),
        )
    } catch (e: CancellationException) {
        throw e
    } catch (e: ApiException) {
        if ((e.error as? AppError.Http)?.status == 404) Result.success(null) else Result.failure(e)
    } catch (e: Throwable) {
        Result.failure(ApiException(e.appError))
    }

    /** `POST /api/services/<name>/start` (F11-R4, F10-R5). */
    suspend fun start(name: String): Result<Unit> = apiCall {
        api.request(method = "POST", path = Endpoints.serviceStart(name), deserializer = ServiceActionResponseDto.serializer())
        Unit
    }

    /** `POST /api/services/<name>/stop` (F11-R3, F10-R5). */
    suspend fun stop(name: String): Result<Unit> = apiCall {
        api.request(method = "POST", path = Endpoints.serviceStop(name), deserializer = ServiceActionResponseDto.serializer())
        Unit
    }

    /**
     * `GET /api/services/<name>/logs` (F12-R3) — the one-shot fallback, used
     * when the stream cannot be established. Lines are split client-side on
     * `\n` rather than trusting the server's own `lines` count.
     */
    suspend fun fetchLogsOnce(name: String, tail: Int = 200): Result<List<String>> = apiCall {
        api.get(
            Endpoints.serviceLogs(name),
            ServiceLogsResponseDto.serializer(),
            query = mapOf("tail" to tail.toString()),
        ).logs.split("\n")
    }
}
