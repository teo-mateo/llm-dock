package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.data.dto.PiSessionDto
import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.data.model.PiState

fun PiSessionDto.toDomain(): PiSession = PiSession(
    key = PiSessionKey(sessionId, instanceId),
    name = name,
    cwd = cwd,
    model = model,
    thinkingLevel = thinkingLevel,
    firstSeen = firstSeen,
    lastSeen = lastSeen,
    endedAt = endedAt,
    endReason = endReason,
    live = live,
    state = when {
        !live -> PiState.ENDED
        state == "working" -> PiState.WORKING
        else -> PiState.IDLE
    },
    contextPercent = contextPercent,
)
