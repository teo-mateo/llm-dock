package com.hpz.llmdockchat.core.auth

import com.hpz.llmdockchat.core.net.BaseUrl

/** Old unbound ciphertext does not decode, so upgrading requires one fresh sign-in. */
internal data class ServerBoundSecret<T>(val server: BaseUrl, val secret: T) {
    fun encode(encodeSecret: (T) -> String): String = "v1\n${server.value}\n${encodeSecret(secret)}"

    companion object {
        fun <T> decode(raw: String, decodeSecret: (String) -> T?): ServerBoundSecret<T>? {
            val parts = raw.split('\n', limit = 3)
            if (parts.size != 3 || parts[0] != "v1") return null
            val server = BaseUrl.restore(parts[1]) ?: return null
            val secret = decodeSecret(parts[2]) ?: return null
            return ServerBoundSecret(server, secret)
        }
    }
}
