package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.data.dto.ArtifactDto
import com.hpz.llmdockchat.data.dto.ChatMessageDto
import com.hpz.llmdockchat.data.dto.ConversationDetailDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * `GET /api/chat/conversations/<id>` carries artifacts as a sibling of
 * `messages` — `{message_id: [Artifact, …]}` — not nested on the message
 * (`chat/routes.py`, `chat/db.py:get_artifacts_for_conversation`). F05-R6/R8
 * render these, so the mapper folding them onto the right message by id is
 * what makes that possible.
 */
class ChatThreadMapperTest {

    private fun message(id: String, seq: Int) =
        ChatMessageDto(id = id, role = "assistant", content = "answer $seq", seq = seq)

    @Test
    fun `an artifact is folded onto the message it belongs to, by id`() {
        val dto = ConversationDetailDto(
            id = "c1",
            title = "t",
            mainService = "llamacpp-laguna-s-2.1-q4",
            messages = listOf(message("m1", 1), message("m2", 2)),
            artifacts = mapOf(
                "m2" to listOf(ArtifactDto(id = "a1", type = "svg", content = "<svg/>", title = "Circuit")),
            ),
        )

        val domain = dto.toDomain()

        assertTrue(domain.messages.first { it.id == "m1" }.artifacts.isEmpty())
        val artifact = domain.messages.first { it.id == "m2" }.artifacts.single()
        assertEquals("svg", artifact.type)
        assertEquals("Circuit", artifact.title)
        assertEquals("<svg/>", artifact.content)
    }

    @Test
    fun `a message with no entry in the artifacts map gets an empty list, not a crash`() {
        val dto = ConversationDetailDto(
            id = "c1",
            title = "t",
            mainService = "llamacpp-laguna-s-2.1-q4",
            messages = listOf(message("m1", 1)),
        )

        val domain = dto.toDomain()

        assertEquals(emptyList<Any>(), domain.messages.single().artifacts)
    }

    /** F08 reads the enabled tool set through this same mapper (Architecture D6). */
    @Test
    fun `mcp_servers is carried through to the domain model`() {
        val dto = ConversationDetailDto(
            id = "c1",
            title = "t",
            mainService = "llamacpp-laguna-s-2.1-q4",
            mcpServers = listOf("sympy-math", "websearch"),
        )

        assertEquals(listOf("sympy-math", "websearch"), dto.toDomain().mcpServers)
    }

    @Test
    fun `a missing mcp_servers key maps to an empty list`() {
        val dto = ConversationDetailDto(id = "c1", title = "t", mainService = "llamacpp-laguna-s-2.1-q4")

        assertEquals(emptyList<String>(), dto.toDomain().mcpServers)
    }

    /**
     * F15-R4: the level is read off the detail payload, and "model default"
     * must survive as `null` — not `""`, which the mapper would then treat as a
     * level name, and not `"off"`, which is an opposite instruction.
     */
    @Test
    fun `a stored reasoning level is carried through to the domain model`() {
        val dto = decodeDetail("""{"id":"c1","title":"t","main_service":"vllm-a","reasoning_level":"medium"}""")

        assertEquals("medium", dto.toDomain().reasoningLevel)
    }

    @Test
    fun `an absent or null reasoning_level both map to null, never an empty string`() {
        assertEquals(null, decodeDetail("""{"id":"c1","title":"t","main_service":"vllm-a"}""").toDomain().reasoningLevel)
        assertEquals(null, decodeDetail("""{"id":"c1","title":"t","main_service":"vllm-a","reasoning_level":null}""").toDomain().reasoningLevel)
    }
}

private fun decodeDetail(json: String): ConversationDetailDto =
    ApiJson.decodeFromString(ConversationDetailDto.serializer(), json)
