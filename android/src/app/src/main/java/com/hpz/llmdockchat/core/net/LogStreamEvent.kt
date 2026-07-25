package com.hpz.llmdockchat.core.net

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * One typed frame from `GET /api/services/<name>/logs/stream` (F12-R1). The
 * `: keepalive` comment frame never reaches here — [SseFrameParser] drops any
 * line starting with `:` before a payload is ever assembled.
 *
 * Pure and total, same contract as [parseServiceStreamFrame] and
 * [parseGpuStreamFrame]: nothing here ever throws.
 */
sealed interface LogStreamEvent {
    /** The historical tail is about to start. */
    data object SnapshotStart : LogStreamEvent

    /** One log line, verbatim — never reordered, never truncated (F12-R4's third criterion). */
    data class Log(val line: String) : LogStreamEvent

    /** The tail is done; anything after this is live output (F12-R1's second criterion). */
    data object SnapshotEnd : LogStreamEvent

    /** The container's log stream ended — an end state, not a failure (F12-R1's fourth criterion). */
    data object StreamEnd : LogStreamEvent

    data class Error(val message: String) : LogStreamEvent

    /** An unrecognised `type`, or a payload that is not JSON at all. */
    data class Unknown(val raw: String) : LogStreamEvent
}

private val LogStreamJson = Json { ignoreUnknownKeys = true }

fun parseLogStreamFrame(payload: String): LogStreamEvent {
    val root = runCatching { LogStreamJson.parseToJsonElement(payload.trim()) }.getOrNull() as? JsonObject
        ?: return LogStreamEvent.Unknown(payload)

    return when (root.stringField("type")) {
        "snapshot_start" -> LogStreamEvent.SnapshotStart
        "log" -> root.stringField("line")?.let { LogStreamEvent.Log(it) } ?: LogStreamEvent.Unknown(payload)
        "snapshot_end" -> LogStreamEvent.SnapshotEnd
        "stream_end" -> LogStreamEvent.StreamEnd
        "error" -> LogStreamEvent.Error(root.stringField("message") ?: "Unknown error")
        else -> LogStreamEvent.Unknown(payload)
    }
}

private fun JsonObject.stringField(key: String): String? =
    (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content
