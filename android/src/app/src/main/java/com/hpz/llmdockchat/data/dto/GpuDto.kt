package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One GPU from `GET /api/gpu` / `GET /api/gpu/stream` (`dashboard/docker_utils.py:get_gpu_stats`).
 * The real payload also carries clocks, fan speed and a performance state —
 * F10-R3 only asks for VRAM, utilisation, temperature and power, so those are
 * the only fields modelled here; anything else is ignored by
 * `ignoreUnknownKeys` rather than given a place to go unused.
 */
@Serializable
data class GpuDto(
    val index: Int = 0,
    val name: String = "",
    val memory: GpuMemoryDto = GpuMemoryDto(),
    val temperature: GpuTemperatureDto = GpuTemperatureDto(),
    val utilization: GpuUtilizationDto = GpuUtilizationDto(),
    val power: GpuPowerDto = GpuPowerDto(),
)

@Serializable
data class GpuMemoryDto(
    val total: Int = 0,
    val used: Int = 0,
)

@Serializable
data class GpuTemperatureDto(val current: Int = 0)

@Serializable
data class GpuUtilizationDto(@SerialName("gpu_percent") val gpuPercent: Int = 0)

@Serializable
data class GpuPowerDto(
    val draw: Double = 0.0,
    val limit: GpuPowerLimitDto = GpuPowerLimitDto(),
)

/** Only [enforced] is shown — the actual cap in effect, not the card's factory default/max. */
@Serializable
data class GpuPowerLimitDto(val enforced: Double = 0.0)

@Serializable
data class GpuListResponseDto(val gpus: List<GpuDto> = emptyList())
