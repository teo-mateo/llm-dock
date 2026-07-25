package com.hpz.llmdockchat.data.model

/**
 * A conversation's `main_service`, normalised once at the wire↔domain seam
 * (Architecture D6) instead of every screen re-parsing the `openrouter:`
 * prefix for itself.
 */
sealed interface ModelRef {
    /** A local Docker service — `vllm-…`, `llamacpp-…`, `ds4-…`, or anything else. */
    data class Local(val serviceName: String) : ModelRef

    /** `openrouter:<model-id>` — the id is what the UI shows, never the raw string. */
    data class OpenRouter(val modelId: String) : ModelRef
}

/** What a row/chip displays. For [ModelRef.OpenRouter] this is the model id, not `openrouter:<id>`. */
val ModelRef.displayName: String
    get() = when (this) {
        is ModelRef.Local -> serviceName
        is ModelRef.OpenRouter -> modelId
    }

private const val OPENROUTER_PREFIX = "openrouter:"

/** Parses a raw `main_service` string into a [ModelRef]. Blank input is a [ModelRef.Local] of "". */
fun parseModelRef(raw: String): ModelRef =
    if (raw.startsWith(OPENROUTER_PREFIX)) {
        ModelRef.OpenRouter(raw.removePrefix(OPENROUTER_PREFIX))
    } else {
        ModelRef.Local(raw)
    }

/** The inverse of [parseModelRef] — what F03 sends as `main_service` on create. */
val ModelRef.wireValue: String
    get() = when (this) {
        is ModelRef.Local -> serviceName
        is ModelRef.OpenRouter -> "$OPENROUTER_PREFIX$modelId"
    }
