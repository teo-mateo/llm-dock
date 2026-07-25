package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.Serializable

/** One row of `GET /api/services` (`dashboard/docker_utils.py:get_docker_services`). Only the
 * fields F03's model picker needs. */
@Serializable
data class ServiceDto(
    val name: String = "",
    val status: String = "",
    val kind: String = "",
)

@Serializable
data class ServiceListResponseDto(val services: List<ServiceDto> = emptyList())
