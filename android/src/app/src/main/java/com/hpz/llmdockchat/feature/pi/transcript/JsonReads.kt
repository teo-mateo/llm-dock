package com.hpz.llmdockchat.feature.pi.transcript

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

internal fun JsonObject.str(key: String): String? =
    (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

internal fun JsonObject.long(key: String): Long? =
    (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.content?.toLongOrNull()

internal fun JsonObject.bool(key: String): Boolean =
    (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.content?.toBooleanStrictOrNull() ?: false

internal fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject
