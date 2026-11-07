package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.data.dto.PiEventDto
import com.hpz.llmdockchat.data.dto.PiSessionDto
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

sealed interface PiSessionStreamEvent {
    data class Events(val events: List<PiEventDto>) : PiSessionStreamEvent
    data class Session(val session: PiSessionDto) : PiSessionStreamEvent
    data class Lagged(val after: Long) : PiSessionStreamEvent
    data class Removed(val sessionId: String, val instanceId: String) : PiSessionStreamEvent
    data class Unknown(val raw: String) : PiSessionStreamEvent
}

private val PiSessionJson = Json { ignoreUnknownKeys = true }

fun parsePiSessionStreamFrame(payload: String): PiSessionStreamEvent {
    val root = runCatching { PiSessionJson.parseToJsonElement(payload.trim()) }.getOrNull() as? JsonObject
        ?: return PiSessionStreamEvent.Unknown(payload)

    return when (root.stringField("type")) {
        "events" -> {
            val eventsElement = root["events"] as? JsonArray ?: return PiSessionStreamEvent.Unknown(payload)
            val events = runCatching {
                PiSessionJson.decodeFromJsonElement(ListSerializer(PiEventDto.serializer()), eventsElement)
            }.getOrNull() ?: return PiSessionStreamEvent.Unknown(payload)
            PiSessionStreamEvent.Events(events)
        }
        "session" -> {
            val session = runCatching {
                PiSessionJson.decodeFromJsonElement(PiSessionDto.serializer(), root)
            }.getOrNull() ?: return PiSessionStreamEvent.Unknown(payload)
            PiSessionStreamEvent.Session(session)
        }
        "session_removed" -> {
            val sessionId = root.stringField("session_id")
                ?: return PiSessionStreamEvent.Unknown(payload)
            val instanceId = root.stringField("instance_id")
                ?: return PiSessionStreamEvent.Unknown(payload)
            PiSessionStreamEvent.Removed(sessionId, instanceId)
        }
        "lagged" -> {
            val after = root.longField("after") ?: return PiSessionStreamEvent.Unknown(payload)
            PiSessionStreamEvent.Lagged(after)
        }
        else -> PiSessionStreamEvent.Unknown(payload)
    }
}

private fun JsonObject.stringField(key: String): String? =
    (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

private fun JsonObject.longField(key: String): Long? =
    (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.content?.toLongOrNull()
