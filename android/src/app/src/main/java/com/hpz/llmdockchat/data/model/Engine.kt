package com.hpz.llmdockchat.data.model

/**
 * The four engines the dashboard colour-codes its badges by (F02-R2), plus
 * [UNKNOWN] for a service name with no recognised prefix — a thread pointing
 * at a deleted or renamed service must still render, unstyled, not crash the
 * row.
 */
enum class Engine { LLAMA_CPP, VLLM, DS4, OPEN_ROUTER, UNKNOWN }

/** Derived from the [ModelRef.Local] name prefix, or [Engine.OPEN_ROUTER] for a remote model. */
val ModelRef.engine: Engine
    get() = when (this) {
        is ModelRef.OpenRouter -> Engine.OPEN_ROUTER
        is ModelRef.Local -> when {
            serviceName.startsWith("vllm-") -> Engine.VLLM
            serviceName.startsWith("llamacpp-") -> Engine.LLAMA_CPP
            serviceName.startsWith("ds4-") -> Engine.DS4
            else -> Engine.UNKNOWN
        }
    }
