package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.data.dto.ActiveRunDto
import com.hpz.llmdockchat.data.dto.ArtifactDto
import com.hpz.llmdockchat.data.dto.ChatMessageDto
import com.hpz.llmdockchat.data.dto.ConversationDetailDto
import com.hpz.llmdockchat.data.dto.LastRunDto
import com.hpz.llmdockchat.data.dto.ParseWarningDto
import com.hpz.llmdockchat.data.dto.ToolCallDto
import com.hpz.llmdockchat.data.model.ActiveRun
import com.hpz.llmdockchat.data.model.ArtifactRecord
import com.hpz.llmdockchat.data.model.ChatMessage
import com.hpz.llmdockchat.data.model.ConversationDetail
import com.hpz.llmdockchat.data.model.LastRun
import com.hpz.llmdockchat.data.model.ParseWarning
import com.hpz.llmdockchat.data.model.ToolCallRecord
import com.hpz.llmdockchat.data.model.parseMessageRole
import com.hpz.llmdockchat.data.model.parseModelRef
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive

fun ConversationDetailDto.toDomain(): ConversationDetail = ConversationDetail(
    id = id,
    title = title,
    modelRef = parseModelRef(mainService),
    // The server orders by seq already; sorting here makes the list's own
    // ordering independent of that, since `key` stability drives recomposition.
    messages = messages.sortedBy { it.seq }.map { it.toDomain(artifacts[it.id].orEmpty()) },
    activeRun = activeRun?.toActiveRun(),
    lastRun = lastRun?.toLastRun(),
    updatedAt = updatedAt,
)

private fun ChatMessageDto.toDomain(artifacts: List<ArtifactDto>): ChatMessage = ChatMessage(
    id = id,
    role = parseMessageRole(role),
    content = content,
    reasoning = reasoningContent?.takeIf { it.isNotBlank() },
    modelService = modelService,
    images = images,
    seq = seq,
    createdAt = createdAt,
    toolCalls = toolCalls.map { it.toDomain() },
    parseWarning = parseWarning?.toDomain(),
    error = error?.takeIf { it.isNotBlank() },
    artifacts = artifacts.map { it.toDomain() },
)

private fun ArtifactDto.toDomain(): ArtifactRecord =
    ArtifactRecord(type = type, title = title, content = content, language = language)

private fun ToolCallDto.toDomain(): ToolCallRecord = ToolCallRecord(
    name = name,
    arguments = arguments.render(),
    // A persisted call only grows a `result` key once the tool answered, so a
    // missing one means "never completed", not "returned nothing".
    result = result?.render(),
    serverId = serverId,
)

private fun ParseWarningDto.toDomain(): ParseWarning =
    ParseWarning(kind = kind, description = description, snippet = snippet?.takeIf { it.isNotBlank() })

private fun ActiveRunDto.toActiveRun(): ActiveRun? {
    val runId = id ?: return null
    val runStatus = status ?: return null
    return ActiveRun(id = runId, status = runStatus, activeStep = activeStep, startedAt = startedAt)
}

private fun LastRunDto.toLastRun(): LastRun? {
    val runId = id ?: return null
    val runStatus = status ?: return null
    return LastRun(id = runId, status = runStatus, error = error?.takeIf { it.isNotBlank() })
}

/** Same collapse as the stream parser's: these values are only ever displayed. */
private fun JsonElement?.render(): String = when (this) {
    null -> ""
    is JsonPrimitive -> content
    else -> toString()
}
