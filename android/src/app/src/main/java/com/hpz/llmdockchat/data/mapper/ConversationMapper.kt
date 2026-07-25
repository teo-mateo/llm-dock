package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.data.dto.ActiveRunDto
import com.hpz.llmdockchat.data.dto.ConversationDto
import com.hpz.llmdockchat.data.model.ActiveRun
import com.hpz.llmdockchat.data.model.ConversationSummary
import com.hpz.llmdockchat.data.model.parseModelRef

fun ConversationDto.toDomain(): ConversationSummary = ConversationSummary(
    id = id,
    title = title,
    modelRef = parseModelRef(mainService),
    updatedAt = updatedAt,
    activeRun = activeRun?.toDomain(),
)

private fun ActiveRunDto.toDomain(): ActiveRun? {
    // A run with no id or status is not something the UI can act on or show —
    // treat it the same as a missing active_run rather than rendering a blank
    // indicator.
    val runId = id ?: return null
    val runStatus = status ?: return null
    return ActiveRun(id = runId, status = runStatus, activeStep = activeStep, startedAt = startedAt)
}
