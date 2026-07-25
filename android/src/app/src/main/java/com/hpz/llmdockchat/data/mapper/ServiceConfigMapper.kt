package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.data.dto.ServiceConfigDto
import com.hpz.llmdockchat.data.model.ServiceConfig
import kotlinx.serialization.json.JsonPrimitive

fun ServiceConfigDto.toDomain(): ServiceConfig = ServiceConfig(
    modelPath = modelPath,
    modelName = modelName,
    // `params`' values are usually plain strings ("" for a bare flag), but the
    // server never guarantees that on the wire, so render the same way the
    // stream parser does elsewhere rather than assume and risk a decode crash.
    flags = params.map { (flag, value) -> flag to value.render() },
    templateType = templateType,
    modelSizeStr = modelSizeStr,
)

private fun kotlinx.serialization.json.JsonElement.render(): String = when (this) {
    is JsonPrimitive -> content
    else -> toString()
}
