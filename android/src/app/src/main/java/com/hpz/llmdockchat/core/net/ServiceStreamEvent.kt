package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.data.dto.ServiceDto
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull

/**
 * One frame of `GET /api/services/stream` (F07-R1's third criterion), read the
 * same way [parseFrame] reads a chat run — pure, total, dependency-light — but
 * this is its own parser, not a reuse of [parseFrame]: the two endpoints share
 * nothing but "SSE" (`dashboard/routes/services.py:services_stream`, not
 * `chat/run_manager.py`).
 *
 * [Delta] deliberately carries only [serviceName], [status] and [favorite] —
 * the three fields a picker actually needs to update in place
 * (`ComposeManagerEvent`'s `action`/`container_id`/`timestamp` are not read).
 * Neither this type nor [Snapshot] (via [ServiceDto]) ever has a field for
 * `api_key`, so one cannot leak through here even by accident (F07-R6).
 */
sealed interface ServiceStreamEvent {

    /** Always the first frame on connect — the full service list as it stands right now. */
    data class Snapshot(val services: List<ServiceDto>) : ServiceStreamEvent

    /** A container's status changed, or its `favorite` flag did, elsewhere (dashboard or another client). */
    data class Delta(val serviceName: String, val status: String?, val favorite: Boolean?) : ServiceStreamEvent

    data class Error(val message: String) : ServiceStreamEvent

    /** An unrecognised `type`, or a payload that is not JSON at all — never thrown, always this. */
    data class Unknown(val raw: String) : ServiceStreamEvent
}

private val ServiceStreamJson = Json { ignoreUnknownKeys = true }

/** Pure, total, no IO — same contract as [parseFrame]. Every input produces an event; nothing throws. */
fun parseServiceStreamFrame(payload: String): ServiceStreamEvent {
    val root = runCatching { ServiceStreamJson.parseToJsonElement(payload.trim()) }.getOrNull() as? JsonObject
        ?: return ServiceStreamEvent.Unknown(payload)

    return when (root.string("type")) {
        "snapshot" -> root.snapshotFrame(payload)
        "delta" -> root.deltaFrame(payload)
        "error" -> ServiceStreamEvent.Error(root.string("message") ?: "Unknown error")
        else -> ServiceStreamEvent.Unknown(payload)
    }
}

private fun JsonObject.snapshotFrame(payload: String): ServiceStreamEvent {
    val data = this["data"] as? JsonObject ?: return ServiceStreamEvent.Unknown(payload)
    val servicesElement = data["services"] ?: return ServiceStreamEvent.Unknown(payload)
    val services = runCatching {
        ServiceStreamJson.decodeFromJsonElement(ListSerializer(ServiceDto.serializer()), servicesElement)
    }.getOrNull() ?: return ServiceStreamEvent.Unknown(payload)
    return ServiceStreamEvent.Snapshot(services)
}

private fun JsonObject.deltaFrame(payload: String): ServiceStreamEvent {
    val name = string("service_name") ?: return ServiceStreamEvent.Unknown(payload)
    val metadata = this["metadata"] as? JsonObject
    return ServiceStreamEvent.Delta(
        serviceName = name,
        status = string("status"),
        favorite = (metadata?.get("favorite") as? JsonPrimitive)?.booleanOrNull,
    )
}

private fun JsonObject.string(key: String): String? =
    (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content
