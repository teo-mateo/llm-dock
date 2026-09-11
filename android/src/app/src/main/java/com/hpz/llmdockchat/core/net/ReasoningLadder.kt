package com.hpz.llmdockchat.core.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * The one tolerant reader for a service's declared reasoning levels (F15).
 *
 * `reasoning_levels` arrives as `[{"id": "low", "effort": "low"}, …]` on both
 * `GET /api/services` and its SSE snapshot, and inside a `metadata-changed`
 * delta. Only `id` is read — `effort` is the request-side token, which the
 * server sets equal to `id` and this client has no use for.
 *
 * The wire type is deliberately a bare [JsonElement] rather than
 * `List<ReasoningLevelDto>`, and this function never throws. A typed list would
 * fail at *decode* on an entry like `["junk"]`, which in
 * `ServiceStreamEvent.snapshotFrame` means the `runCatching` swallows the
 * **whole** payload into `Unknown` and the model picker stops updating — a far
 * larger loss than one service with no ladder. So the shape is checked here,
 * entry by entry: non-objects, a missing/non-string/blank `id` and duplicates
 * are dropped, declaration order is kept, and everything else in the row
 * survives.
 *
 * No grammar is validated, on purpose: the server already collapses an invalid
 * declaration to `[]` (`dashboard/docker_utils.py:_parsed_reasoning_levels`),
 * and a Kotlin copy of `validate_levels` would only create a second authority
 * that can disagree with the one that enforces levels at run time.
 */
fun parseReasoningLevels(element: JsonElement?): List<String> {
    val array = element as? JsonArray ?: return emptyList()
    val ids = mutableListOf<String>()
    array.forEach { entry ->
        val id = (entry as? JsonObject)?.get("id") as? JsonPrimitive ?: return@forEach
        if (id is JsonNull) return@forEach
        val value = id.takeIf { it.isString }?.content ?: return@forEach
        if (value.isNotBlank() && value !in ids) ids.add(value)
    }
    return ids
}
