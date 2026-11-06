package com.hpz.llmdockchat.data.model

/**
 * A conversation's `main_service`, normalised once at the wire↔domain seam
 * instead of every screen re-parsing the `openrouter:`
 * prefix for itself.
 */
sealed interface ModelRef {
    /** A local Docker service — `vllm-…`, `llamacpp-…`, `ds4-…`, or anything else. */
    data class Local(val serviceName: String) : ModelRef

    /** `openrouter:<model-id>` — the id is what the UI shows, never the raw string. */
    data class OpenRouter(val modelId: String) : ModelRef

    /** `<provider-id>:<model-id>`, the grammar of the server's `chat/providers.py:parse_service`. */
    data class Provider(val providerId: String, val modelId: String) : ModelRef
}

/** What a row/chip displays. For [ModelRef.OpenRouter] this is the model id, not `openrouter:<id>`. */
val ModelRef.displayName: String
    get() = when (this) {
        is ModelRef.Local -> serviceName
        is ModelRef.OpenRouter -> modelId
        is ModelRef.Provider -> modelId
    }

fun ModelRef.providerLabel(providerNames: Map<String, String> = emptyMap()): String? =
    (this as? ModelRef.Provider)?.let { providerNames[it.providerId]?.takeIf(String::isNotBlank) ?: it.providerId }

fun ModelRef.chipLabel(providerNames: Map<String, String> = emptyMap()): String =
    providerLabel(providerNames)?.let { "$it · $displayName" } ?: displayName

private const val OPENROUTER_PREFIX = "openrouter:"

private val PROVIDER_ID = Regex("^[a-z][a-z0-9-]{1,31}$")

/** Parses a raw `main_service` string into a [ModelRef]. Blank input is a [ModelRef.Local] of "". */
fun parseModelRef(raw: String): ModelRef {
    if (raw.startsWith(OPENROUTER_PREFIX)) return ModelRef.OpenRouter(raw.removePrefix(OPENROUTER_PREFIX))
    val colon = raw.indexOf(':')
    if (colon > 0) {
        val providerId = raw.substring(0, colon)
        val modelId = raw.substring(colon + 1)
        if (modelId.isNotEmpty() && PROVIDER_ID.matches(providerId)) return ModelRef.Provider(providerId, modelId)
    }
    return ModelRef.Local(raw)
}

/** The inverse of [parseModelRef] — what is sent as `main_service` on create. */
val ModelRef.wireValue: String
    get() = when (this) {
        is ModelRef.Local -> serviceName
        is ModelRef.OpenRouter -> "$OPENROUTER_PREFIX$modelId"
        is ModelRef.Provider -> "$providerId:$modelId"
    }
