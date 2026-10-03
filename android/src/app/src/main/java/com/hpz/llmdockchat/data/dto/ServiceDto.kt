package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/**
 * One row of `GET /api/services` (`dashboard/docker_utils.py:get_docker_services`). The model pickers only need the first five
  * fields; the models list also
 * needs [exitCode], [modelSizeStr] and [created] to show an exited service's
 * code and a size/created-ago label. Still no
 * `api_key` field: the server includes one on every row, and the fastest way
 * to guarantee it never reaches a screen or a log line is to
 * never give it a place to land.
 */
@Serializable
data class ServiceDto(
    val name: String = "",
    val status: String = "",
    val kind: String = "",
    @SerialName("host_port") val hostPort: Int = 0,
    val favorite: Boolean = false,
    @SerialName("exit_code") val exitCode: Int? = null,
    @SerialName("model_size_str") val modelSizeStr: String? = null,
    val created: String? = null,
    /**
     * The levels this service's model accepts, `[{"id","effort"}, …]` in
     * the operator's declaration order. A [JsonElement] rather than a typed
     * list so one unexpected entry costs this service its ladder instead of
     * the whole snapshot — see [com.hpz.llmdockchat.core.net.parseReasoningLevels].
     */
    @SerialName("reasoning_levels") val reasoningLevels: JsonElement? = null,
    /**
     * #269: the service's engine (`"vllm"`, `"ik_llamacpp"`, `"tabbyapi"`, …)
     * — the field that selected its compose template, and the authoritative
     * source for [com.hpz.llmdockchat.data.model.ServiceSummary.engine]. Sent on
     * every row by `get_docker_services`; null on an older snapshot, which falls
     * engine classification back to the name prefix.
     */
    @SerialName("template_type") val templateType: String? = null,
)

@Serializable
data class ServiceListResponseDto(val services: List<ServiceDto> = emptyList())

/**
 * `GET /api/services/<name>` — the stored config, not live status;
 * the detail screen gets status from the same stream as the list.
 * `api_key` is on this payload too and is deliberately not modeled here, same
 * reasoning as [ServiceDto].
 */
@Serializable
data class ServiceConfigDto(
    val alias: String? = null,
    @SerialName("model_path") val modelPath: String? = null,
    @SerialName("model_name") val modelName: String? = null,
    val params: Map<String, JsonElement> = emptyMap(),
    @SerialName("template_type") val templateType: String? = null,
    val port: Int? = null,
    @SerialName("model_size_str") val modelSizeStr: String? = null,
)

@Serializable
data class ServiceDetailResponseDto(
    @SerialName("service_name") val serviceName: String = "",
    val config: ServiceConfigDto = ServiceConfigDto(),
)

/** `{"success": true, ...}` from `control_service`. Only [success]
 * is read — a failure surfaces as a non-2xx, handled by [com.hpz.llmdockchat.core.net.ApiClient] before this ever decodes. */
@Serializable
data class ServiceActionResponseDto(val success: Boolean = true)

/** `GET /api/services/<name>/logs` — the one-shot fallback blob, used
 * when the stream cannot be established. [logs] is the raw tail, timestamped,
 * newline-separated; this client splits it client-side rather than trusting
 * [lines], which counts entries the server split on its own newline. */
@Serializable
data class ServiceLogsResponseDto(
    val service: String = "",
    val logs: String = "",
    val lines: Int = 0,
    val timestamp: String = "",
)
