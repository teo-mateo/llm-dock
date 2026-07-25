package com.hpz.llmdockchat.data.mapper

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
}
