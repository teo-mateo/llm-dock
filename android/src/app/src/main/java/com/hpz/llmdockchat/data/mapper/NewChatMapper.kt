package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.core.net.parseReasoningLevels
import com.hpz.llmdockchat.data.dto.McpServerDto
import com.hpz.llmdockchat.data.dto.OpenRouterModelDto
import com.hpz.llmdockchat.data.dto.PromptDto
import com.hpz.llmdockchat.data.dto.ProviderModelsResponseDto
import com.hpz.llmdockchat.data.dto.ServiceDto
import com.hpz.llmdockchat.data.model.ManagedPrompt
import com.hpz.llmdockchat.data.model.McpServerInfo
import com.hpz.llmdockchat.data.model.ModelOption
import com.hpz.llmdockchat.data.model.ProviderGroup
import com.hpz.llmdockchat.data.model.ServiceSummary

fun ServiceDto.toDomain(): ServiceSummary =
    ServiceSummary(
        name = name,
        status = status,
        kind = kind,
        port = hostPort,
        favorite = favorite,
        exitCode = exitCode,
        modelSizeStr = modelSizeStr,
        createdAt = created,
        reasoningLevels = parseReasoningLevels(reasoningLevels),
        templateType = templateType,
    )

fun PromptDto.toDomain(): ManagedPrompt = ManagedPrompt(id = id, name = name, sortOrder = sortOrder)

fun McpServerDto.toDomain(): McpServerInfo =
    McpServerInfo(id = id, name = name, description = description, icon = icon)

fun OpenRouterModelDto.toDomain(): ModelOption.Remote =
    ModelOption.Remote(
        modelId = id,
        label = label.ifBlank { id },
        reasoningLevels = parseReasoningLevels(reasoningLevels),
    )

fun ProviderModelsResponseDto.toGroups(): List<ProviderGroup> =
    providers
        .filter { it.configured && it.error == null && it.id.isNotBlank() }
        .map { row ->
            val name = row.name.ifBlank { row.id }
            ProviderGroup(
                id = row.id,
                name = name,
                models = row.models.filter { it.id.isNotEmpty() }.map {
                    ModelOption.ProviderModel(
                        providerId = row.id,
                        providerName = name,
                        modelId = it.id,
                        label = it.label.ifBlank { it.id },
                    )
                },
            )
        }
        .filter { it.models.isNotEmpty() }
