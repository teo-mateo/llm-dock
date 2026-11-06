package com.hpz.llmdockchat.feature.pi.transcript
import com.hpz.llmdockchat.data.model.PiEvent
import kotlinx.serialization.json.JsonObject
sealed interface PiItem {
    val id: String
    data class User(override val id: String, val text: String, val imageCount: Int, val fromPhone: Boolean, val ts: Long) : PiItem
    data class Assistant(override val id: String, val text: String, val thinking: String, val streaming: Boolean, val model: String?, val outputTokens: Long?, val stopReason: String?, val ts: Long) : PiItem
    data class Tool(override val id: String, val callId: String, val name: String, val args: String?, val output: String?, val status: ToolStatus, val durationMs: Long?, val truncated: Boolean, val ts: Long) : PiItem
    data class Notice(override val id: String, val text: String, val ts: Long) : PiItem
    data class RunEnd(override val id: String, val outcome: String, val ts: Long) : PiItem
}
enum class ToolStatus { RUNNING, DONE, ERROR }
data class PiTranscript(val items: List<PiItem>, val working: Boolean)
fun buildPiTranscript(events: List<PiEvent>): PiTranscript {
    val builder = TranscriptBuilder()
    events.forEach { builder.apply(it) }
    return PiTranscript(builder.items.toList(), builder.working)
}
private class TranscriptBuilder {
    val items = mutableListOf<PiItem>()
    var working = false
    private var openIndex: Int? = null
    private val toolIndexes = mutableMapOf<String, Int>()
    fun apply(event: PiEvent) {
        when (event.type) {
            "state" -> working = event.payload.str("state") == "working"
            "user_message" -> {
                closeOpen()
                items += PiItem.User(
                    id = "u${event.seq}",
                    text = event.payload.str("text") ?: "",
                    imageCount = event.payload.long("image_count")?.toInt() ?: 0,
                    fromPhone = event.payload.str("origin") == "extension",
                    ts = event.ts,
                )
            }
            "assistant_delta" -> applyDelta(event)
            "assistant_message" -> applyMessage(event)
            "tool_start" -> applyToolStart(event)
            "tool_update", "tool_end" -> applyToolEnd(event)
            "run_end" -> {
                closeOpen()
                items += PiItem.RunEnd(
                    id = "r${event.seq}",
                    outcome = event.payload.str("outcome") ?: "",
                    ts = event.ts,
                )
            }
            else -> {
                val text = noticeText(event.type, event.payload)
                if (text != null) items += PiItem.Notice("n${event.seq}", text, event.ts)
            }
        }
    }
    private fun applyDelta(event: PiEvent) {
        val text = event.payload.str("text") ?: ""
        val thinking = event.payload.str("thinking") ?: ""
        val index = openIndex
        if (index == null) {
            items += assistantItem(
                seq = event.seq,
                ts = event.ts,
                text = text,
                thinking = thinking,
                streaming = true,
                model = null,
                outputTokens = null,
                stopReason = null,
            )
            openIndex = items.lastIndex
        } else {
            val current = items[index] as PiItem.Assistant
            items[index] = current.copy(
                text = current.text + text,
                thinking = current.thinking + thinking,
            )
        }
    }
    private fun applyMessage(event: PiEvent) {
        val text = event.payload.str("text") ?: ""
        val thinking = event.payload.str("thinking") ?: ""
        val model = modelLabel(event.payload.obj("model"))
        val outputTokens = event.payload.obj("usage")?.long("output")
        val stopReason = event.payload.str("stop_reason")
        val index = openIndex
        if (index == null) {
            items += assistantItem(
                seq = event.seq,
                ts = event.ts,
                text = text,
                thinking = thinking,
                streaming = false,
                model = model,
                outputTokens = outputTokens,
                stopReason = stopReason,
            )
        } else {
            val current = items[index] as PiItem.Assistant
            items[index] = current.copy(
                text = text,
                thinking = thinking,
                streaming = false,
                model = model,
                outputTokens = outputTokens,
                stopReason = stopReason,
            )
            openIndex = null
        }
    }
    private fun applyToolStart(event: PiEvent) {
        closeOpen()
        val callId = event.payload.str("call_id") ?: ""
        val tool = PiItem.Tool(
            id = "t$callId",
            callId = callId,
            name = event.payload.str("name") ?: "",
            args = event.payload.str("args"),
            output = null,
            status = ToolStatus.RUNNING,
            durationMs = null,
            truncated = event.payload.bool("truncated"),
            ts = event.ts,
        )
        items += tool
        toolIndexes[callId] = items.lastIndex
    }

    private fun applyToolEnd(event: PiEvent) {
        val callId = event.payload.str("call_id") ?: ""
        val index = toolIndexes[callId]
        if (index == null) {
            val isEnd = event.type == "tool_end"
            val tool = PiItem.Tool(
                id = "t$callId",
                callId = callId,
                name = event.payload.str("name") ?: "",
                args = null,
                output = if (isEnd) event.payload.str("result") else event.payload.str("partial"),
                status = if (isEnd) {
                    if (event.payload.bool("is_error")) ToolStatus.ERROR else ToolStatus.DONE
                } else {
                    ToolStatus.RUNNING
                },
                durationMs = if (isEnd) event.payload.long("duration_ms") else null,
                truncated = event.payload.bool("truncated"),
                ts = event.ts,
            )
            items += tool
            toolIndexes[callId] = items.lastIndex
        } else {
            val current = items[index] as PiItem.Tool
            items[index] = if (event.type == "tool_update") {
                current.copy(
                    output = event.payload.str("partial"),
                    truncated = current.truncated || event.payload.bool("truncated"),
                )
            } else {
                current.copy(
                    output = event.payload.str("result"),
                    status = if (event.payload.bool("is_error")) ToolStatus.ERROR else ToolStatus.DONE,
                    durationMs = event.payload.long("duration_ms"),
                    truncated = current.truncated || event.payload.bool("truncated"),
                )
            }
        }
    }

    private fun closeOpen() {
        val index = openIndex ?: return
        val current = items[index] as PiItem.Assistant
        if (current.streaming) items[index] = current.copy(streaming = false)
        openIndex = null
    }

    private fun assistantItem(seq: Long, ts: Long, text: String, thinking: String, streaming: Boolean, model: String?, outputTokens: Long?, stopReason: String?): PiItem.Assistant = PiItem.Assistant(
        id = "a$seq", text = text, thinking = thinking, streaming = streaming, model = model, outputTokens = outputTokens, stopReason = stopReason, ts = ts,
    )
}

private fun modelLabel(model: JsonObject?): String? =
    model?.let { "${it.str("provider").orEmpty()}/${it.str("id").orEmpty()}" }

private fun noticeText(type: String, payload: JsonObject): String? = when (type) {
    "model_changed" ->
        "Model: ${modelLabel(payload.obj("previous")) ?: "—"} → ${modelLabel(payload.obj("model")) ?: "—"}"
    "thinking_changed" ->
        "Thinking: ${payload.str("previous").orDash()} → ${payload.str("level").orDash()}"
    "compaction" -> {
        val tokens = payload.long("tokens_before")
        if (tokens == null) "Context compacted" else "Context compacted ($tokens tokens)"
    }
    "gap" -> {
        val from = payload.long("from_seq") ?: 0L
        val to = payload.long("to_seq") ?: 0L
        "${to - from + 1} events missing ($from–$to)"
    }
    else -> null
}

private fun String?.orDash(): String = this?.takeIf { it.isNotBlank() } ?: "—"
