package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/**
 * One row of `GET /api/services` (`dashboard/docker_utils.py:get_docker_services`). F03's and
 * F07's model pickers only need the first five fields; F10's models list also
 * needs [exitCode], [modelSizeStr] and [created] to show an exited service's
 * code and a size/created-ago label (F10-R1, F10-R4's Deviations). Still no
 * `api_key` field: the server includes one on every row, and the fastest way
 * to guarantee it never reaches a screen or a log line (F07-R6/F10-R7) is to
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
)

@Serializable
data class ServiceListResponseDto(val services: List<ServiceDto> = emptyList())

/**
 * `GET /api/services/<name>` (F11-R2) — the stored config, not live status;
 * the detail screen gets status from the same stream as the list (F11-R1).
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

/** `{"success": true, ...}` from `control_service` (F11-R3/R4). Only [success]
 * is read — a failure surfaces as a non-2xx, handled by [com.hpz.llmdockchat.core.net.ApiClient] before this ever decodes. */
@Serializable
data class ServiceActionResponseDto(val success: Boolean = true)
