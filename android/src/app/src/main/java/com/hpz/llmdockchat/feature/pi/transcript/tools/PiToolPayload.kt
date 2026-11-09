package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.arr
import com.hpz.llmdockchat.feature.pi.transcript.bool
import com.hpz.llmdockchat.feature.pi.transcript.obj
import com.hpz.llmdockchat.feature.pi.transcript.str
import java.util.Base64
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

data class ToolImage(val mimeType: String, val base64: String)

data class ToolResult(
    val text: String,
    val images: List<ToolImage>,
    val details: JsonObject?,
    val structured: JsonObject?,
    val isError: Boolean,
)

fun parseToolArgs(raw: String?): JsonObject? {
    if (raw == null) return null
    return runCatching { Json.parseToJsonElement(raw) }.getOrNull() as? JsonObject
}

fun parseToolResult(raw: String?): ToolResult? {
    if (raw == null) return null
    return when (val element = runCatching { Json.parseToJsonElement(raw) }.getOrNull()) {
        is JsonObject -> element.arr("content")?.let { envelope(element, it) } ?: verbatim(raw)
        is JsonPrimitive -> if (element.isString) ToolResult(element.content, emptyList(), null, null, false) else verbatim(raw)
        else -> verbatim(raw)
    }
}

fun ToolImage.byteSize(): Int =
    runCatching { Base64.getDecoder().decode(base64).size }.getOrDefault(0)

private fun verbatim(raw: String) = ToolResult(raw, emptyList(), null, null, false)

private fun envelope(root: JsonObject, content: JsonArray): ToolResult {
    val text = content.mapNotNull { part ->
        val entry = part as? JsonObject ?: return@mapNotNull null
        if (entry.str("type") != "text") return@mapNotNull null
        entry.str("text")
    }.joinToString("\n")
    val images = content.mapNotNull { part ->
        val entry = part as? JsonObject ?: return@mapNotNull null
        if (entry.str("type") != "image") return@mapNotNull null
        val data = entry.str("data") ?: return@mapNotNull null
        ToolImage(entry.str("mimeType") ?: "image/png", data)
    }
    return ToolResult(text, images, root.obj("details"), root.obj("structuredContent"), root.bool("isError"))
}
