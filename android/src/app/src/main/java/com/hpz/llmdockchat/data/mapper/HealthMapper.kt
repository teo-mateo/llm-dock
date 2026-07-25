package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.data.dto.HealthDto
import com.hpz.llmdockchat.data.model.ServerHealth

fun HealthDto.toDomain(): ServerHealth = ServerHealth(
    healthy = status.equals("healthy", ignoreCase = true),
    status = status,
    version = version?.takeIf { it.isNotBlank() },
    dockerAvailable = dockerAvailable,
    nvidiaAvailable = nvidiaAvailable,
)
