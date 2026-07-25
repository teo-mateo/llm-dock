package com.hpz.llmdockchat.core.net

import kotlinx.serialization.json.Json

/**
 * `ignoreUnknownKeys` is not a convenience here: the dashboard is under active
 * development and adds fields without a client release (Architecture D2).
 */
val ApiJson: Json = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    coerceInputValues = true
}
