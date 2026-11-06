package com.hpz.llmdockchat.feature.pi.transcript

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

private const val MAX_SUMMARY_CHARS = 160

sealed interface PiDisplayItem {
    val id: String

    data class Single(val item: PiItem) : PiDisplayItem {
        override val id: String get() = item.id
    }

    data class ToolGroup(override val id: String, val tools: List<PiItem.Tool>) : PiDisplayItem
}

fun groupToolRuns(items: List<PiItem>): List<PiDisplayItem> {
    val out = mutableListOf<PiDisplayItem>()
    var tools: MutableList<PiItem.Tool>? = null
    fun flush() {
        tools?.let { out.add(PiDisplayItem.ToolGroup("g${it.first().id}", it.toList())) }
        tools = null
    }
    for (item in items) {
        when {
            item is PiItem.Tool -> (tools ?: mutableListOf<PiItem.Tool>().also { tools = it }).add(item)
            tools != null && item.isQuietAssistant() -> Unit
            else -> {
                flush()
                out.add(PiDisplayItem.Single(item))
            }
        }
    }
    flush()
    return out
}

private fun PiItem.isQuietAssistant(): Boolean =
    this is PiItem.Assistant && !streaming && text.isBlank()

fun argsSummary(args: String?): String {
    if (args == null) return ""
    val flat = objectSummary(args).replace(Regex("\\s+"), " ").trim()
    return if (flat.length > MAX_SUMMARY_CHARS) flat.take(MAX_SUMMARY_CHARS) + "…" else flat
}

private fun objectSummary(args: String): String {
    val parsed = runCatching { Json.parseToJsonElement(args) }.getOrNull() as? JsonObject ?: return args
    return parsed.entries.joinToString(" · ") { (key, value) ->
        val text = if (value is JsonPrimitive && value.isString) value.content else value.toString()
        "$key=$text"
    }
}
