package com.hpz.llmdockchat.feature.pi.transcript

import com.hpz.llmdockchat.data.model.PiEvent
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PiTranscriptContinuationTest {
    private fun event(seq: Long, type: String, payload: String = "{}") =
        PiEvent(seq, type, seq * 1000, Json.parseToJsonElement(payload).jsonObject)

    private val history = listOf(
        event(1, "state", """{"state":"working"}"""),
        event(2, "user_message", """{"text":"hi","image_count":1,"origin":"extension"}"""),
        event(3, "assistant_delta", """{"text":"Hel","thinking":"th"}"""),
        event(4, "compaction", """{"tokens_before":42}"""),
        event(5, "model_changed", """{"model":{"provider":"p","id":"m"}}"""),
        event(6, "gap", """{"from_seq":7,"to_seq":9}"""),
        event(10, "assistant_delta", """{"text":"lo","thinking":"ink"}"""),
        event(11, "assistant_message", """{"text":"Hello!","thinking":"thought","usage":{"output":8}}"""),
        event(12, "tool_start", """{"call_id":"c","name":"read","args":"file"}"""),
        event(13, "tool_update", """{"call_id":"c","partial":"part","truncated":true}"""),
        event(14, "tool_end", """{"call_id":"c","result":"done","duration_ms":9}"""),
        event(15, "tool_update", """{"call_id":"c","partial":"after completion"}"""),
        event(16, "tool_start", """{"call_id":"c","name":"write"}"""),
        event(17, "tool_end", """{"call_id":"c","result":"error","is_error":true}"""),
        event(18, "tool_end", """{"call_id":"unknown","name":"bash","result":"orphan"}"""),
        event(19, "tool_update", """{"call_id":"unknown","partial":"updated"}"""),
        event(20, "assistant_delta", """{"text":"bye"}"""),
        event(21, "thinking_changed", """{"level":"high"}"""),
        event(22, "run_end", """{"outcome":"completed"}"""),
        event(23, "state", """{"state":"idle"}"""),
        event(24, "future"),
        event(25, "assistant_delta", """{"text":"open"}"""),
        event(26, "compaction"),
    )

    @Test
    fun `every split restores the same transcript and continuation as from zero`() {
        val full = TranscriptBuilder().apply { history.forEach { apply(it) } }
        for (split in 0..history.size) {
            val prefix = TranscriptBuilder().apply { history.take(split).forEach { apply(it) } }
            val restored = TranscriptBuilder(prefix.checkpoint())
            history.drop(split).forEach { restored.apply(it) }
            assertEquals("split $split", full.checkpoint(), restored.checkpoint())
            assertEquals("split $split", buildPiTranscript(history), restored.transcript())
        }
    }

    @Test
    fun `restoring after every event preserves all tool mappings and open assistant`() {
        var builder = TranscriptBuilder()
        history.forEach {
            builder.apply(it)
            builder = TranscriptBuilder(builder.checkpoint())
        }
        val tools = builder.transcript().items.filterIsInstance<PiItem.Tool>()
        assertEquals(3, tools.size)
        assertEquals(listOf("after completion", "error", "updated"), tools.map { it.output })
        assertEquals(listOf(ToolStatus.DONE, ToolStatus.ERROR, ToolStatus.DONE), tools.map { it.status })
        assertTrue(tools[0].truncated)
        assertEquals(9L, tools[0].durationMs)
        assertNull(tools[2].args)
        assertEquals("a25", builder.checkpoint().openAssistantId)
        assertFalse(builder.transcript().working)
    }

    @Test
    fun `notice after open assistant does not become continuation target`() {
        val builder = TranscriptBuilder()
        history.take(6).forEach { builder.apply(it) }
        val checkpoint = builder.checkpoint()
        assertTrue(checkpoint.items.last() is PiItem.Notice)
        assertEquals("a3", checkpoint.openAssistantId)
        val restored = TranscriptBuilder(checkpoint)
        restored.apply(history[6])
        val assistant = restored.transcript().items.filterIsInstance<PiItem.Assistant>().single()
        assertEquals("Hello", assistant.text)
        assertEquals("think", assistant.thinking)
        restored.apply(history[7])
        assertEquals("Hello!", (restored.transcript().items[1] as PiItem.Assistant).text)
        assertNull(restored.checkpoint().openAssistantId)
    }

    @Test
    fun `published transcripts and checkpoints never change under subsequent updates`() {
        val builder = TranscriptBuilder()
        val snapshots = history.map {
            builder.apply(it)
            builder.transcript() to builder.checkpoint()
        }
        snapshots.forEachIndexed { index, (transcript, checkpoint) ->
            assertEquals("snapshot $index", buildPiTranscript(history.take(index + 1)), transcript)
            assertEquals(transcript, TranscriptBuilder(checkpoint).transcript())
        }
    }

    @Test
    fun `restored builder does not share input list ownership`() {
        val items = buildPiTranscript(history.take(4)).items.toMutableList()
        val restored = TranscriptBuilder(PiTranscriptCheckpoint(items, true, "a3"))
        items.clear()
        assertEquals(3, restored.transcript().items.size)
        assertTrue(restored.transcript().working)
        assertEquals("a3", restored.checkpoint().openAssistantId)
    }

    @Test
    fun `empty checkpoint continues like empty history`() {
        val builder = TranscriptBuilder(TranscriptBuilder().checkpoint())
        assertEquals(PiTranscript(emptyList(), false), builder.transcript())
        assertNull(builder.checkpoint().openAssistantId)
        history.forEach { builder.apply(it) }
        assertEquals(buildPiTranscript(history), builder.transcript())
    }

    @Test
    fun `restore rejects missing non-assistant or closed continuation`() {
        val invalid = listOf(
            PiTranscriptCheckpoint(emptyList(), false, "missing"),
            PiTranscriptCheckpoint(listOf(PiItem.Notice("n1", "notice", 1)), false, "n1"),
            PiTranscriptCheckpoint(buildPiTranscript(history.take(8)).items, false, "a3"),
        )
        invalid.forEach { checkpoint ->
            assertTrue(runCatching { TranscriptBuilder(checkpoint) }.exceptionOrNull() is IllegalArgumentException)
        }
    }
}
