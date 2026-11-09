package com.hpz.llmdockchat.feature.pi.transcript.tools

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

fun JsonObject.str(key: String): String? =
    (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

fun JsonObject.int(key: String): Int? =
    (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.content?.toIntOrNull()

fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject

fun JsonObject.arr(key: String): JsonArray? = this[key] as? JsonArray

fun ToolImage.byteSize(): Int =
    runCatching { Base64.getDecoder().decode(base64).size }.getOrDefault(0)

internal fun JsonObject.bool(key: String): Boolean =
    (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.content?.toBooleanStrictOrNull() ?: false

private fun verbatim(raw: String) = ToolResult(raw, emptyList(), null, null, false)

private fun envelope(obj: JsonObject, content: JsonArray): ToolResult {
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
    return ToolResult(text, images, obj.obj("details"), obj.obj("structuredContent"), obj.bool("isError"))
}
