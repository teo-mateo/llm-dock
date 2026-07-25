package com.hpz.llmdockchat.core.net

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull

/**
 * One frame of a chat run's SSE stream, as a domain value (Architecture D2).
 *
 * The same three endpoints produce the same frames — `POST …/messages`,
 * `PUT …/messages/<id>` and `GET /api/chat/runs/<id>/stream` — so one reader
 * serves all of them.
 *
 * Two frames carry no `type` key at all, which is why [parseFrame] cannot
 * dispatch on `type` alone: a content [Delta] is the raw upstream OpenAI chunk
 * forwarded verbatim (`chat/event_codec.py:encode_sse_delta`), and [Failed] is
 * the bare `{"error": "…"}` shape.
 */
sealed interface RunEvent {

    /** Always the first frame, synthesized by `observe()` before the worker starts. */
    data class RunStarted(val runId: String) : RunEvent

    /**
     * Text. Either half may be empty: models emit reasoning first and content
     * after, and a reattach's replay folds a whole run of deltas into one frame
     * carrying both.
     */
    data class Delta(val content: String, val reasoning: String) : RunEvent

    /** The model started a tool call; [name] is `<server_id>__<tool>` here, unlike [ToolCall]. */
    data class ToolCallPending(val index: Int, val name: String) : RunEvent

    /** The full call, about to execute. [arguments] is rendered JSON, ready to show. */
    data class ToolCall(val name: String, val arguments: String, val serverId: String?) : RunEvent

    /** What the tool returned. [result] is rendered JSON or the bare string. */
    data class ToolResult(val name: String, val result: String, val serverId: String?) : RunEvent

    /** [artifactType] is `svg`, `image`, `html` or `code` (F05 renders these). */
    data class Artifact(val artifactType: String, val title: String?, val content: String) : RunEvent

    /** The model emitted a malformed tool call — `{kind, snippet, description}`. */
    data class ParseWarning(val kind: String?, val description: String?, val snippet: String?) : RunEvent

    /** Liveness during slow generation. Not content. */
    data class Heartbeat(val elapsedSeconds: Double) : RunEvent

    /** `data: [DONE]`. Model output finished — but the stream does **not** end here. */
    data object Done : RunEvent

    /** The assistant turn is durable. Follows [Done]. */
    data class MessageSaved(val messageId: String, val seq: Int) : RunEvent

    /** The auto-generated title. Can arrive after [MessageSaved]. */
    data class ConversationUpdated(val id: String, val title: String) : RunEvent

    /**
     * The run failed. Unlike a cancel, the server **has** persisted whatever
     * text accumulated, plus this error (`ChatRunner._fail`).
     */
    data class Failed(val message: String) : RunEvent

    /**
     * The observer closed on the run's durable status rather than on a live
     * event — either a reattach to an already-terminal run, or the send path's
     * backstop firing while the auto-title tail is still running.
     */
    data class RunStatus(val status: String, val error: String?) : RunEvent

    /**
     * A frame this client does not recognise. Mandatory, not a fallback of last
     * resort: the dashboard adds typed frames without an app release, and a
     * parser that threw would turn a harmless new frame into a dead chat
     * screen. Also covers a payload that is not JSON at all.
     */
    data class Unknown(val raw: String) : RunEvent
}

private const val DONE_SENTINEL = "[DONE]"

/**
 * Lenient by construction: delta frames are upstream model output whose shape
 * is not ours to control.
 */
private val FrameJson = Json {
    ignoreUnknownKeys = true
    isLenient = true
}

/**
 * Pure, total, no IO (Architecture D2). Every input produces a [RunEvent];
 * nothing throws.
 */
fun parseFrame(payload: String): RunEvent {
    val trimmed = payload.trim()
    if (trimmed == DONE_SENTINEL) return RunEvent.Done

    val root = runCatching { FrameJson.parseToJsonElement(trimmed) }.getOrNull() as? JsonObject
        ?: return RunEvent.Unknown(payload)

    // A `type` this build knows wins, and so does an `error` — but neither
    // shadows `choices` when it does not resolve. A delta is raw upstream model
    // output whose shape is not ours to control: one that grew a top-level
    // `type` the app has never heard of must still be read as text rather than
    // discarded as Unknown.
    root.string("type")?.let { type -> root.typedFrame(type)?.let { return it } }
    root.string("error")?.let { return RunEvent.Failed(it) }
    if (root["choices"] is JsonArray) return root.deltaFrame()
    return RunEvent.Unknown(payload)
}

/** Null when the type is unrecognised, or a required field is missing. */
private fun JsonObject.typedFrame(type: String): RunEvent? = when (type) {
    "run_started" -> string("run_id")?.let { RunEvent.RunStarted(it) }
    "tool_call_pending" -> string("name")?.let { RunEvent.ToolCallPending(int("index") ?: 0, it) }
    "tool_call" -> string("name")?.let {
        RunEvent.ToolCall(it, rendered("arguments"), string("server_id"))
    }
    "tool_result" -> string("name")?.let {
        RunEvent.ToolResult(it, rendered("result"), string("server_id"))
    }
    "artifact" -> string("artifact_type")?.let {
        RunEvent.Artifact(it, string("title"), rendered("content"))
    }
    "parse_warning" -> RunEvent.ParseWarning(string("kind"), string("description"), string("snippet"))
    "heartbeat" -> RunEvent.Heartbeat(double("elapsed_s") ?: 0.0)
    "message_saved" -> string("message_id")?.let { RunEvent.MessageSaved(it, int("seq") ?: 0) }
    "conversation_updated" -> string("id")?.let { RunEvent.ConversationUpdated(it, string("title").orEmpty()) }
    "run_status" -> string("status")?.let { RunEvent.RunStatus(it, string("error")) }
    else -> null
}

/**
 * A raw OpenAI-compatible chunk. Reasoning arrives as `reasoning_content` from
 * llama.cpp and as `reasoning` from some other models (Architecture D6), so
 * both are read.
 */
private fun JsonObject.deltaFrame(): RunEvent {
    val delta = (this["choices"] as? JsonArray)
        ?.firstOrNull()
        ?.let { it as? JsonObject }
        ?.get("delta") as? JsonObject
        ?: return RunEvent.Delta("", "")
    return RunEvent.Delta(
        content = delta.string("content").orEmpty(),
        reasoning = delta.string("reasoning_content") ?: delta.string("reasoning").orEmpty(),
    )
}

private fun JsonObject.string(key: String): String? =
    (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

private fun JsonObject.int(key: String): Int? = (this[key] as? JsonPrimitive)?.intOrNull

private fun JsonObject.double(key: String): Double? = (this[key] as? JsonPrimitive)?.doubleOrNull

/**
 * Tool arguments, tool results and artifact bodies are typed on the wire — a
 * JSON object for `arguments`, usually a string for `result`. Both are only
 * ever displayed, so they collapse to one displayable string here rather than
 * leaking a `JsonElement` into the UI.
 */
private fun JsonObject.rendered(key: String): String = when (val value = this[key]) {
    null -> ""
    is JsonPrimitive -> value.content
    else -> value.toString()
}
