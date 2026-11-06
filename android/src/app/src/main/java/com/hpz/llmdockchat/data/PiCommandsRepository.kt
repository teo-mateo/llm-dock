package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.data.dto.PiCommandResponseDto
import com.hpz.llmdockchat.data.dto.PiMessageRequestDto
import com.hpz.llmdockchat.data.model.PiCommandOutcome
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.data.model.Rejection
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.encodeToString

open class PiCommandsRepository(private val api: ApiClient) {

    open suspend fun send(key: PiSessionKey, text: String): PiCommandOutcome = execute {
        api.request(
            method = "POST",
            path = Endpoints.piSessionMessages(key.sessionId, key.instanceId),
            deserializer = PiCommandResponseDto.serializer(),
            body = ApiJson.encodeToString(PiMessageRequestDto(text)),
        )
    }

    open suspend fun abort(key: PiSessionKey): PiCommandOutcome = execute {
        api.request(
            method = "POST",
            path = Endpoints.piSessionAbort(key.sessionId, key.instanceId),
            deserializer = PiCommandResponseDto.serializer(),
            body = "{}",
        )
    }

    private suspend fun execute(block: suspend () -> PiCommandResponseDto): PiCommandOutcome =
        try {
            success(block())
        } catch (e: CancellationException) {
            throw e
        } catch (e: ApiException) {
            failure(e.error)
        }

    private fun success(response: PiCommandResponseDto): PiCommandOutcome = when {
        response.ok == true -> PiCommandOutcome.Done
        response.ok == false -> PiCommandOutcome.Failed(response.error)
        response.pending == true -> PiCommandOutcome.Pending
        else -> PiCommandOutcome.Rejected(Rejection.OTHER)
    }

    private fun failure(error: AppError): PiCommandOutcome = when (error) {
        is AppError.Http -> when (error.status) {
            409 -> PiCommandOutcome.Rejected(Rejection.OFFLINE)
            429 -> PiCommandOutcome.Rejected(Rejection.RATE_LIMITED)
            503 -> PiCommandOutcome.Rejected(Rejection.BUSY)
            400 -> if (error.message == "invalid_text") {
                PiCommandOutcome.Rejected(Rejection.INVALID_TEXT)
            } else {
                PiCommandOutcome.Rejected(Rejection.OTHER)
            }
            else -> PiCommandOutcome.Rejected(Rejection.OTHER)
        }
        else -> PiCommandOutcome.Rejected(Rejection.OTHER)
    }
}
