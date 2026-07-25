package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.data.dto.GpuDto
import com.hpz.llmdockchat.data.model.GpuSummary

fun GpuDto.toDomain(): GpuSummary = GpuSummary(
    index = index,
    name = name,
    memoryUsedMiB = memory.used,
    memoryTotalMiB = memory.total,
    utilizationPercent = utilization.gpuPercent,
    temperatureC = temperature.current,
    powerDrawW = power.draw,
    powerLimitW = power.limit.enforced,
)
