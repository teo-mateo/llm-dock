package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.data.dto.McpServerDto
import com.hpz.llmdockchat.data.dto.OpenRouterModelDto
import com.hpz.llmdockchat.data.dto.PromptDto
import com.hpz.llmdockchat.data.dto.ServiceDto
import com.hpz.llmdockchat.data.model.ManagedPrompt
import com.hpz.llmdockchat.data.model.McpServerInfo
import com.hpz.llmdockchat.data.model.ModelOption
import com.hpz.llmdockchat.data.model.ServiceSummary

fun ServiceDto.toDomain(): ServiceSummary =
    ServiceSummary(name = name, status = status, kind = kind, port = hostPort, favorite = favorite)

fun PromptDto.toDomain(): ManagedPrompt = ManagedPrompt(id = id, name = name, sortOrder = sortOrder)

fun McpServerDto.toDomain(): McpServerInfo =
    McpServerInfo(id = id, name = name, description = description, icon = icon)

/** Falls back to the id when [OpenRouterModelDto.label] is blank — it's optional server-side. */
fun OpenRouterModelDto.toDomain(): ModelOption.Remote =
    ModelOption.Remote(modelId = id, label = label.ifBlank { id })
