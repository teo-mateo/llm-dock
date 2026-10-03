package com.hpz.llmdockchat.data.model

/**
 * The seven engines the dashboard colour-codes its badges by, plus
 * [Engine.OPEN_ROUTER] for a hosted model and [Engine.UNKNOWN] for a service it
 * cannot classify — a thread pointing at a deleted or renamed service must still
 * render, unstyled, not crash the row. The seven are every engine the dashboard
 * renders a compose template for (`dashboard/flag_metadata.py`); a service on any
 * of them is chat-capable once its `kind` is chat.
 */
enum class Engine { LLAMA_CPP, IK_LLAMA_CPP, VLLM, DS4, TABBYAPI, NINFER, SGLANG, OPEN_ROUTER, UNKNOWN }

/**
 * Maps the dashboard's `template_type` — the authoritative engine id carried on
 * every service payload (`docker_utils.get_docker_services`) — to an [Engine], or
 * null when it names none we know. Preferred over [ModelRef.engine]'s name-prefix
 * guess: the prefix is a display convention a rename can change, this is the value
 * that selected the service's compose template.
 */
fun engineFromTemplateType(templateType: String?): Engine? = when (templateType) {
    "vllm" -> Engine.VLLM
    "llamacpp" -> Engine.LLAMA_CPP
    "ik_llamacpp" -> Engine.IK_LLAMA_CPP
    "ds4" -> Engine.DS4
    "tabbyapi" -> Engine.TABBYAPI
    "ninfer" -> Engine.NINFER
    "sglang" -> Engine.SGLANG
    else -> null
}

/**
 * Derived from the [ModelRef.Local] name prefix — the fallback classification when
 * no `template_type` is at hand (a stored conversation points at a name, not a
 * template). [Engine.OPEN_ROUTER] for a remote model. The prefixes mirror the
 * dashboard's `SERVICE_NAME_PREFIXES`: `ik-` for ik_llama.cpp, `exl3-` for TabbyAPI.
 */
val ModelRef.engine: Engine
    get() = when (this) {
        is ModelRef.OpenRouter -> Engine.OPEN_ROUTER
        is ModelRef.Local -> when {
            serviceName.startsWith("vllm-") -> Engine.VLLM
            serviceName.startsWith("llamacpp-") -> Engine.LLAMA_CPP
            serviceName.startsWith("ik-") -> Engine.IK_LLAMA_CPP
            serviceName.startsWith("ds4-") -> Engine.DS4
            serviceName.startsWith("exl3-") -> Engine.TABBYAPI
            serviceName.startsWith("ninfer-") -> Engine.NINFER
            serviceName.startsWith("sglang-") -> Engine.SGLANG
            else -> Engine.UNKNOWN
        }
    }
