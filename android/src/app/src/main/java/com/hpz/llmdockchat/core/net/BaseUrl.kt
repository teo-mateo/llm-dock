package com.hpz.llmdockchat.core.net

import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * The one configured server address. Constructed only through
 * [BaseUrl.normalize], so anything holding a [BaseUrl] holds a canonical,
 * parseable origin with no trailing slash and no `/api` suffix.
 */
@JvmInline
value class BaseUrl private constructor(val value: String) {

    fun resolve(path: String, query: Map<String, String> = emptyMap()): HttpUrl {
        val builder = value.toHttpUrl().newBuilder()
        path.split('/').filter { it.isNotEmpty() }.forEach { builder.addPathSegment(it) }
        query.forEach { (key, value) -> builder.addQueryParameter(key, value) }
        return builder.build()
    }

    override fun toString(): String = value

    companion object {
        private val SCHEME = Regex("^[a-zA-Z][a-zA-Z0-9+.\\-]*://")

        /**
         * Turn whatever the user typed into a base URL, or explain why it
         * cannot be one. Absorbs surrounding whitespace, a missing scheme,
         * trailing slashes, and an `/api` suffix pasted from a browser.
         */
        fun normalize(raw: String): BaseUrlResult {
            val trimmed = raw.trim()
            if (trimmed.isEmpty()) return BaseUrlResult.Invalid("Enter a server address.")

            val withScheme = if (SCHEME.containsMatchIn(trimmed)) trimmed else "http://$trimmed"
            val parsed = withScheme.toHttpUrlOrNull()
                ?: return BaseUrlResult.Invalid("That is not a valid http:// or https:// address.")
            if (parsed.host.isBlank()) {
                return BaseUrlResult.Invalid("That address has no host.")
            }

            var segments = parsed.pathSegments.filter { it.isNotEmpty() }
            if (segments.lastOrNull().equals("api", ignoreCase = true)) {
                segments = segments.dropLast(1)
            }

            val canonical = buildString {
                append(parsed.scheme).append("://").append(parsed.host)
                if (parsed.port != HttpUrl.defaultPort(parsed.scheme)) {
                    append(':').append(parsed.port)
                }
                segments.forEach { append('/').append(it) }
            }
            return BaseUrlResult.Valid(BaseUrl(canonical))
        }

        /** For a value already known to be canonical (e.g. read back from storage). */
        fun restore(stored: String): BaseUrl? = (normalize(stored) as? BaseUrlResult.Valid)?.baseUrl
    }
}

sealed interface BaseUrlResult {
    data class Valid(val baseUrl: BaseUrl) : BaseUrlResult
    data class Invalid(val reason: String) : BaseUrlResult
}
