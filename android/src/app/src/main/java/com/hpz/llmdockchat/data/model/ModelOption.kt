package com.hpz.llmdockchat.data.model

sealed interface ModelOption {
    val ref: ModelRef

    data class LocalService(val serviceName: String, val status: String) : ModelOption {
        override val ref: ModelRef get() = ModelRef.Local(serviceName)
        val isRunning: Boolean get() = status == "running"
    }

    data class Remote(
        val modelId: String,
        val label: String,
        val reasoningLevels: List<String> = emptyList(),
    ) : ModelOption {
        override val ref: ModelRef get() = ModelRef.OpenRouter(modelId)
    }
}

data class OpenRouterAvailability(val configured: Boolean, val models: List<ModelOption.Remote>)
