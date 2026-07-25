package com.hpz.llmdockchat.core.net

import com.hpz.llmdockchat.data.dto.GpuDto
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * One frame of `GET /api/gpu/stream` (`dashboard/routes/gpu.py:gpu_stream`). Unlike
 * `services_stream` this endpoint has no `type` envelope — every tick is either
 * `{"gpus": […], "timestamp": …}` or, when `nvidia-smi` itself failed that tick,
 * `{"error": …}`. Pure and total, same contract as [parseServiceStreamFrame]:
 * nothing here ever throws.
 */
sealed interface GpuStreamEvent {
    data class Frame(val gpus: List<GpuDto>) : GpuStreamEvent
    data class Error(val message: String) : GpuStreamEvent
    data class Unknown(val raw: String) : GpuStreamEvent
}

private val GpuStreamJson = Json { ignoreUnknownKeys = true }

fun parseGpuStreamFrame(payload: String): GpuStreamEvent {
    val root = runCatching { GpuStreamJson.parseToJsonElement(payload.trim()) }.getOrNull() as? JsonObject
        ?: return GpuStreamEvent.Unknown(payload)

    // Checked before "gpus": an error tick carries no gpus key at all
    // (`gpu_stream`'s except branch yields only `{"error": str(e)}`).
    (root["error"] as? JsonPrimitive)?.takeIf { it.isString }?.let {
        return GpuStreamEvent.Error(it.content)
    }

    val gpusElement = root["gpus"] ?: return GpuStreamEvent.Unknown(payload)
    val gpus = runCatching {
        GpuStreamJson.decodeFromJsonElement(ListSerializer(GpuDto.serializer()), gpusElement)
    }.getOrNull() ?: return GpuStreamEvent.Unknown(payload)
    return GpuStreamEvent.Frame(gpus)
}
