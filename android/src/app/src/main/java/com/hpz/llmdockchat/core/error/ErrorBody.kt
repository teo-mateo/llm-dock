package com.hpz.llmdockchat.core.error

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * The dashboard reports failures as `{"error": "..."}` (see `dashboard/auth.py`
 * and every route blueprint). Some upstream proxies nest it as
 * `{"error": {"message": "..."}}`, so both shapes are accepted.
 */
object ErrorBody {

    private val json = Json { ignoreUnknownKeys = true }

    /** The server's own words, or null when the body carries none. */
    fun extract(body: String?): String? {
        val text = body?.trim().orEmpty()
        if (text.isEmpty()) return null
        val root = runCatching { json.parseToJsonElement(text) }.getOrNull() as? JsonObject
            ?: return null
        return root.message("error") ?: root.message("message") ?: root.message("detail")
    }

    private fun JsonObject.message(key: String): String? {
        return when (val value = this[key]) {
            is JsonPrimitive -> value.contentOrNullIfNotString()
            is JsonObject -> value.message("message")
            else -> null
        }
    }

    private fun JsonPrimitive.contentOrNullIfNotString(): String? =
        if (isString) content.takeIf { it.isNotBlank() } else null
}
