package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.data.dto.PiSessionDto
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

sealed interface PiSessionsStreamEvent {
    data class Snapshot(val sessions: List<PiSessionDto>) : PiSessionsStreamEvent
    data class Session(val session: PiSessionDto) : PiSessionsStreamEvent
    data class Removed(val sessionId: String, val instanceId: String) : PiSessionsStreamEvent
    data object Lagged : PiSessionsStreamEvent
    data class Unknown(val raw: String) : PiSessionsStreamEvent
}

private val PiSessionsJson = Json { ignoreUnknownKeys = true }

fun parsePiSessionsStreamFrame(payload: String): PiSessionsStreamEvent {
    val root = runCatching { PiSessionsJson.parseToJsonElement(payload.trim()) }.getOrNull() as? JsonObject
        ?: return PiSessionsStreamEvent.Unknown(payload)

    return when (root.stringField("type")) {
        "snapshot" -> {
            val sessionsElement = root["sessions"] ?: return PiSessionsStreamEvent.Unknown(payload)
            val sessions = runCatching {
                PiSessionsJson.decodeFromJsonElement(ListSerializer(PiSessionDto.serializer()), sessionsElement)
            }.getOrNull() ?: return PiSessionsStreamEvent.Unknown(payload)
            PiSessionsStreamEvent.Snapshot(sessions)
        }
        "session" -> {
            val session = runCatching {
                PiSessionsJson.decodeFromJsonElement(PiSessionDto.serializer(), root)
            }.getOrNull() ?: return PiSessionsStreamEvent.Unknown(payload)
            PiSessionsStreamEvent.Session(session)
        }
        "session_removed" -> {
            val sessionId = root.stringField("session_id")
                ?: return PiSessionsStreamEvent.Unknown(payload)
            val instanceId = root.stringField("instance_id")
                ?: return PiSessionsStreamEvent.Unknown(payload)
            PiSessionsStreamEvent.Removed(sessionId, instanceId)
        }
        "lagged" -> PiSessionsStreamEvent.Lagged
        else -> PiSessionsStreamEvent.Unknown(payload)
    }
}

private fun JsonObject.stringField(key: String): String? =
    (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content
