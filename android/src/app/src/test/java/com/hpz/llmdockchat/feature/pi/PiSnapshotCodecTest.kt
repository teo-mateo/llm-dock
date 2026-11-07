package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.data.model.PiEvent
import com.hpz.llmdockchat.data.model.PiState
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotCodec
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotLimits
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotTooLarge
import com.hpz.llmdockchat.feature.pi.transcript.TranscriptBuilder
import java.io.ByteArrayOutputStream
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PiSnapshotCodecTest {
    private val codec = PiSnapshotCodec()

    @Test
    fun `all items statuses nullables and continuation survive gzip roundtrip`() {
        val original = snapshot()
        val output = ByteArrayOutputStream()
        codec.write(original, output)
        val restored = codec.read(output.toByteArray().inputStream(), original.identity)!!
        assertEquals(original, restored)
        val builder = TranscriptBuilder(restored.checkpoint)
        builder.apply(PiEvent(21, "assistant_delta", 21, JsonObject(mapOf("text" to JsonPrimitive(" tail")))))
        builder.apply(PiEvent(22, "tool_update", 22, JsonObject(mapOf(
            "call_id" to JsonPrimitive("c"), "partial" to JsonPrimitive("late result"),
        ))))
        val items = builder.transcript().items
        assertEquals("partial λ\nnext tail", (items[6] as PiItem.Assistant).text)
        assertTrue(items.last() is PiItem.Notice)
        assertEquals("late result", (items[2] as PiItem.Tool).output)
        assertEquals("partial λ\nnext", (original.checkpoint.items[6] as PiItem.Assistant).text)
    }

    @Test
    fun `nullable summary and empty checkpoint roundtrip with every session state`() {
        for (state in PiState.entries) {
            val original = snapshot().let { it.copy(
                summary = it.summary.copy(
                    name = null, model = null, thinkingLevel = null, contextPercent = null,
                    endedAt = 300, endReason = "exit", live = false, state = state, prompts = emptyList(),
                ),
                checkpoint = com.hpz.llmdockchat.feature.pi.transcript.PiTranscriptCheckpoint(emptyList(), false, null),
            ) }
            assertEquals(original, codec.read(encodedSnapshot(original).inputStream(), original.identity))
        }
    }

    @Test
    fun `invalid version identity cursor summary or continuation is a miss`() {
        val original = snapshot()
        val invalid = listOf(
            original.copy(version = 0),
            original.copy(version = 2),
            original.copy(lastSeq = -1),
            original.copy(firstSeen = 101),
            original.copy(summary = original.summary.copy(key = snapshotIdentity("other").key)),
            original.copy(identity = snapshotIdentity(server = "HTTPS://EXAMPLE.COM/")),
            original.copy(checkpoint = original.checkpoint.copy(openAssistantId = "missing")),
            original.copy(checkpoint = original.checkpoint.copy(openAssistantId = "n11")),
            original.copy(checkpoint = original.checkpoint.copy(openAssistantId = "a2")),
        )
        invalid.forEach {
            assertNull(it.toString(), codec.read(encodedSnapshot(it).inputStream(), it.identity))
        }
        for (identity in listOf(snapshotIdentity("other"), snapshotIdentity(server = "https://elsewhere.com"),
            original.identity.copy(key = original.identity.key.copy(instanceId = "other")))) {
            assertNull(codec.read(encodedSnapshot(original).inputStream(), identity))
        }
    }

    @Test
    fun `missing version or firstSeen and malformed content are misses while unknown fields are additive`() {
        val original = snapshot()
        val root = snapshotJson.parseToJsonElement(snapshotJson.encodeToString(original)).jsonObject
        val invalid = listOf(
            JsonObject(root - "version").toString(),
            JsonObject(root - "firstSeen").toString(),
            JsonObject(root + ("firstSeen" to JsonNull)).toString(),
            JsonObject(root + ("version" to JsonPrimitive("one"))).toString(),
            "{}", "[]", "null", "not json", root.toString() + " garbage",
        )
        invalid.forEach { assertNull(codec.read(gzip(it.toByteArray()).inputStream(), original.identity)) }
        assertNull(codec.read("not gzip".byteInputStream(), original.identity))
        val invalidUtf8 = snapshotJson.encodeToString(original).toByteArray().apply {
            this[indexOf('λ'.toString().toByteArray()[0])] = 0xff.toByte()
        }
        assertNull(codec.read(gzip(invalidUtf8).inputStream(), original.identity))
        assertNull(codec.read(encodedSnapshot(original).dropLast(4).toByteArray().inputStream(), original.identity))
        val additive = JsonObject(root + ("extra" to JsonPrimitive(42))).toString()
        assertEquals(original, codec.read(gzip(additive.toByteArray()).inputStream(), original.identity))
    }

    @Test
    fun `exact decompressed byte limit succeeds and one additional byte is rejected`() {
        val limit = PiSnapshotLimits().jsonBytes
        val empty = snapshot(text = "")
        val overhead = snapshotJson.encodeToString(empty).toByteArray().size
        val exact = snapshot(text = "x".repeat(limit - overhead))
        val raw = snapshotJson.encodeToString(exact).toByteArray()
        assertEquals(8 * 1024 * 1024, raw.size)
        val output = ByteArrayOutputStream()
        codec.write(exact, output)
        assertEquals(exact, codec.read(output.toByteArray().inputStream(), exact.identity))
        val tooBig = snapshot(text = "x".repeat(limit - overhead + 1))
        assertNull(codec.read(encodedSnapshot(tooBig).inputStream(), tooBig.identity))
        assertTrue(runCatching { codec.write(tooBig, ByteArrayOutputStream()) }.exceptionOrNull() is PiSnapshotTooLarge)
    }

    @Test
    fun `compressed input and output are independently bounded`() {
        val original = snapshot()
        val bytes = encodedSnapshot(original)
        val limited = PiSnapshotCodec(PiSnapshotLimits(committedBytes = bytes.size.toLong() - 1))
        assertNull(limited.read(bytes.inputStream(), original.identity))
        assertTrue(runCatching { limited.write(original, ByteArrayOutputStream()) }.exceptionOrNull() is PiSnapshotTooLarge)
        assertTrue(PiSnapshotCodec(PiSnapshotLimits(committedBytes = bytes.size.toLong()))
            .read(bytes.inputStream(), original.identity) != null)
    }

    @Test
    fun `identity filenames are stable separated and never contain user supplied path segments`() {
        val identity = snapshotIdentity("../../escape/λ")
        assertTrue(identity.fileName().matches(Regex("[0-9a-f]{64}\\.json\\.gz")))
        assertEquals(identity.fileName(), identity.copy().fileName())
        assertEquals(4, setOf(
            identity.fileName(),
            identity.copy(server = "https://other.example").fileName(),
            identity.copy(key = identity.key.copy(sessionId = "other")).fileName(),
            identity.copy(key = identity.key.copy(instanceId = "other")).fileName(),
        ).size)
        assertFalse(snapshotIdentity(server = "https://example.com/").isCanonical())
    }
}
