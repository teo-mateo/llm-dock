package com.hpz.llmdockchat.data.model

/**
 * One selectable entry in the new-chat model picker (F03-R1). A minimal
 * chooser for now: local services from `GET /api/services` plus the curated
 * OpenRouter list from `GET /api/chat/settings/openrouter-models`. F07 owns
 * the full picker (search, favorites, richer grouping); it enriches the
 * screen that renders this list, not this shape.
 */
sealed interface ModelOption {
    val ref: ModelRef

    /** A chat-capable local Docker service. [status] is the server's raw string. */
    data class LocalService(val serviceName: String, val status: String) : ModelOption {
        override val ref: ModelRef get() = ModelRef.Local(serviceName)
        val isRunning: Boolean get() = status == "running"
    }

    /**
     * A curated OpenRouter model. No running/stopped concept — always selectable.
     * [reasoningLevels] is the ladder the server derived for it (F15.1); empty
     * means OpenRouter publishes no `supported_efforts` for this model, which by
     * F15-R7 means no control rather than a default one.
     */
    data class Remote(
        val modelId: String,
        val label: String,
        val reasoningLevels: List<String> = emptyList(),
    ) : ModelOption {
        override val ref: ModelRef get() = ModelRef.OpenRouter(modelId)
    }
}

/**
 * `GET /api/chat/settings/openrouter-models` (F03), trimmed to what the picker
 * needs. [configured] mirrors the dashboard: OpenRouter's group is hidden entirely
 * when `OPENROUTER_API_KEY` isn't set server-side, rather than shown with a list
 * that would fail on selection. Since F15.1 the entries also carry each model's
 * derived ladder, which is what lets a remote thread offer reasoning levels — the
 * phone has no other source for it, as the service stream does not carry remote
 * models.
 */
data class OpenRouterAvailability(val configured: Boolean, val models: List<ModelOption.Remote>)
