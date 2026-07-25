package com.hpz.llmdockchat.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** The body both login routes return: `{"token": "totp-…", "expires_in": 28800}`. */
@Serializable
data class SessionDto(
    val token: String = "",
    @SerialName("expires_in") val expiresIn: Long = 0,
)

/** `POST /api/auth/verify` — `{"valid": true, "message": "Token is valid"}`. */
@Serializable
data class TokenVerificationDto(
    val valid: Boolean = false,
    val message: String? = null,
)
