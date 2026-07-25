package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One row of `GET /api/services` (`dashboard/docker_utils.py:get_docker_services`). Only the
 * fields F03's and F07's model pickers need — in particular, no `api_key` field:
 * the server includes one on every row, and the fastest way to guarantee it
 * never reaches a screen or a log line (F07-R6) is to never give it a place
 * to land.
 */
@Serializable
data class ServiceDto(
    val name: String = "",
    val status: String = "",
    val kind: String = "",
    @SerialName("host_port") val hostPort: Int = 0,
    val favorite: Boolean = false,
)

@Serializable
data class ServiceListResponseDto(val services: List<ServiceDto> = emptyList())
