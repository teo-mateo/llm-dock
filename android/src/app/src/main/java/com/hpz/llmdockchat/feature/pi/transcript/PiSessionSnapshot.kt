package com.hpz.llmdockchat.feature.pi.transcript

import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey
import java.security.MessageDigest
import kotlinx.serialization.Required
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

@Serializable
internal data class PiSnapshotIdentity(val server: String, val key: PiSessionKey) {
    fun fileName(): String = MessageDigest.getInstance("SHA-256")
        .digest(Json.encodeToString(this).toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) } + ".json.gz"

    fun isCanonical(): Boolean = BaseUrl.restore(server)?.value == server
}

@Serializable
internal data class PiSessionSnapshot(
    @Required val version: Int = VERSION,
    val identity: PiSnapshotIdentity,
    val firstSeen: Long,
    val lastSeq: Long,
    val savedAt: Long,
    val summary: PiSession,
    val checkpoint: PiTranscriptCheckpoint,
) {
    fun isValidFor(expected: PiSnapshotIdentity): Boolean =
        version == VERSION && identity == expected && identity.isCanonical() && lastSeq >= 0 &&
            summary.key == identity.key && summary.firstSeen == firstSeen &&
            runCatching { TranscriptBuilder(checkpoint) }.isSuccess

    fun frozen(): PiSessionSnapshot = copy(
        checkpoint = checkpoint.copy(items = checkpoint.items.toList()),
        summary = summary.copy(prompts = summary.prompts.toList()),
    )

    companion object {
        const val VERSION = 1
    }
}

internal data class PiSnapshotLimits(
    val pendingWrites: Int = 8,
    val jsonBytes: Int = 25 * 1024 * 1024,
    val fileBytes: Long = jsonBytes.toLong(),
    val warningBytes: Long = 500L * 1024 * 1024,
) {
    init {
        require(pendingWrites > 0 && jsonBytes > 0 && fileBytes > 0 && warningBytes > 0)
    }
}
