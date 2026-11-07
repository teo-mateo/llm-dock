package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.data.model.PiPrompt
import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.data.model.PiState
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.PiSessionSnapshot
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotIdentity
import com.hpz.llmdockchat.feature.pi.transcript.PiTranscriptCheckpoint
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import java.io.ByteArrayOutputStream
import java.util.zip.GZIPOutputStream
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

internal val snapshotJson = Json { encodeDefaults = true }

internal fun snapshotIdentity(id: String = "session", server: String = "https://example.com") =
    PiSnapshotIdentity(server, PiSessionKey(id, "instance"))

internal fun snapshot(
    identity: PiSnapshotIdentity = snapshotIdentity(),
    seq: Long = 20,
    text: String = "partial λ\nnext",
): PiSessionSnapshot = PiSessionSnapshot(
    identity = identity,
    firstSeen = 100,
    lastSeq = seq,
    savedAt = 200,
    summary = PiSession(
        key = identity.key, name = "Pi session", cwd = "/repo", model = "provider/model",
        thinkingLevel = "high", firstSeen = 100, lastSeen = 200, endedAt = null,
        endReason = null, live = true, state = PiState.WORKING, contextPercent = 42.5,
        prompts = listOf(PiPrompt("prompt", "confirm", null)),
    ),
    checkpoint = PiTranscriptCheckpoint(
        items = listOf(
            PiItem.User("u1", "hello", 2, true, 10),
            PiItem.Assistant("a2", "final", "thought", false, "p/m", 12, "stop", 11),
            PiItem.Tool("tc", "c", "read", "args", "result", ToolStatus.DONE, 8, true, 12),
            PiItem.Tool("tr", "r", "write", null, null, ToolStatus.RUNNING, null, false, 13),
            PiItem.Tool("te", "e", "bash", "{}", "error", ToolStatus.ERROR, 9, false, 14),
            PiItem.RunEnd("r9", "completed", 15),
            PiItem.Assistant("a10", text, "thinking", true, null, null, null, 16),
            PiItem.Notice("n11", "Context compacted", 17),
        ),
        working = true,
        openAssistantId = "a10",
    ),
)

internal fun gzip(bytes: ByteArray): ByteArray = ByteArrayOutputStream().apply {
    GZIPOutputStream(this).use { it.write(bytes) }
}.toByteArray()

internal fun encodedSnapshot(snapshot: PiSessionSnapshot): ByteArray =
    gzip(snapshotJson.encodeToString(snapshot).toByteArray(Charsets.UTF_8))
