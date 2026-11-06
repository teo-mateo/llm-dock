package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.data.dto.PiPromptDto
import com.hpz.llmdockchat.data.dto.PiSessionDto
import com.hpz.llmdockchat.data.model.PiPrompt
import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.data.model.PiState

fun PiPromptDto.toDomain(): PiPrompt = PiPrompt(
    promptId = promptId,
    kind = kind,
    title = title,
)

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
    prompts = prompts.map { it.toDomain() },
)
