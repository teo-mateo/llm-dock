package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.data.dto.OpenRouterModelDto
import com.hpz.llmdockchat.data.dto.ServiceDto
import com.hpz.llmdockchat.data.model.ModelOption
import com.hpz.llmdockchat.data.model.ServiceSummary
import org.junit.Assert.assertEquals
import org.junit.Test

/** [ServiceDto.toDomain] — F07 added `host_port`/`favorite` on top of F03's `name`/`status`/`kind`. */
class NewChatMapperTest {

    @Test
    fun `host_port and favorite map straight through, and api_key has no field to map from`() {
        val dto = ServiceDto(
            name = "llamacpp-a",
            status = "running",
            kind = "chat",
            hostPort = 3301,
            favorite = true,
        )
        assertEquals(
            ServiceSummary(name = "llamacpp-a", status = "running", kind = "chat", port = 3301, favorite = true),
            dto.toDomain(),
        )
    }

    @Test
    fun `defaults are zero and false when the server omits the fields`() {
        val dto = ServiceDto(name = "llamacpp-a", status = "running", kind = "chat")
        val summary = dto.toDomain()
        assertEquals(0, summary.port)
        assertEquals(false, summary.favorite)
    }

    // -- F15: the reasoning ladder ------------------------------------------------

    @Test
    fun `a declared ladder maps through in declaration order`() {
        val summary = decode(
            """{"name": "vllm-a", "status": "running", "kind": "chat",
                 "reasoning_levels": [{"id": "off", "effort": "off"},
                                       {"id": "xhigh", "effort": "xhigh"},
                                       {"id": "low", "effort": "low"}]}""",
        ).toDomain()
        // Order is the operator's meaning, so it is never sorted or deduped by rank.
        assertEquals(listOf("off", "xhigh", "low"), summary.reasoningLevels)
    }

    @Test
    fun `no key and an empty list both mean no ladder`() {
        assertEquals(emptyList<String>(), decode("""{"name": "vllm-a"}""").toDomain().reasoningLevels)
        assertEquals(emptyList<String>(), decode("""{"name": "vllm-a", "reasoning_levels": []}""").toDomain().reasoningLevels)
    }

    /**
     * The tolerant-entry rules, which are the reason the wire type is a
     * JsonElement: each of these would throw at decode against a typed
     * `List<ReasoningLevelDto>`, and the throw is caught one layer above the
     * mapper — where it costs the whole snapshot rather than one row's ladder.
     */
    @Test
    fun `malformed ladder entries are dropped one by one and the valid ones survive`() {
        val summary = decode(
            """{"name": "vllm-a", "status": "running",
                 "reasoning_levels": [{"id": null}, "junk", {}, {"id": "   "},
                                      {"id": "low"}, {"id": "low"}, {"id": "xhigh"}]}""",
        ).toDomain()
        assertEquals(listOf("low", "xhigh"), summary.reasoningLevels)
        // The row itself is still there — a garbage ladder must not lose the service.
        assertEquals("running", summary.status)
    }

    @Test
    fun `a ladder that is not an array at all reads as no ladder`() {
        assertEquals(emptyList<String>(), decode("""{"name": "vllm-a", "reasoning_levels": "off,low"}""").toDomain().reasoningLevels)
    }

    /**
     * F15.1: a remote model's ladder reaches the domain through the same parser a
     * local service's does, which is the whole point of keeping the two wire shapes
     * alike. The absent case matters as much as the present one: a model OpenRouter
     * publishes no efforts for must yield an empty ladder, because an empty ladder
     * is exactly what suppresses the control (F15-R7).
     */
    @Test
    fun `an openrouter entry maps its derived ladder and an absent one maps to empty`() {
        val withLadder = decodeOr(
            """{"id":"a/b","label":"A B","reasoning_levels":[{"id":"low","effort":"low"},""" +
                """{"id":"high","effort":"high"}]}""",
        ).toDomain()
        assertEquals(listOf("low", "high"), withLadder.reasoningLevels)
        assertEquals("A B", withLadder.label)

        val without = decodeOr("""{"id":"a/b","label":"A B"}""").toDomain()
        assertEquals(emptyList<String>(), without.reasoningLevels)
        assertEquals(ModelOption.Remote("a/b", "A B", emptyList()), without)
    }
}

private fun decodeOr(json: String): OpenRouterModelDto =
    ApiJson.decodeFromString(OpenRouterModelDto.serializer(), json)

private fun decode(json: String): ServiceDto = ApiJson.decodeFromString(ServiceDto.serializer(), json)
