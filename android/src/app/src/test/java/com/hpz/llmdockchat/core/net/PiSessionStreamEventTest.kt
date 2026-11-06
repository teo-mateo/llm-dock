package com.hpz.llmdockchat.core.net

import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Test

class PiSessionStreamEventTest {

    @Test
    fun `events frame parses in order`() {
        val payload = """
            {"type":"events","events":[
                {"seq":10,"type":"message","ts":100,"payload":{"text":"first"}},
                {"seq":11,"type":"tool","ts":200,"payload":{"name":"bash"}}
            ]}
        """.trimIndent()

        val event = parsePiSessionStreamFrame(payload) as PiSessionStreamEvent.Events
        assertEquals(listOf(10L, 11L), event.events.map { it.seq })
        assertEquals(listOf("message", "tool"), event.events.map { it.type })
        assertEquals(100L, event.events[0].ts)
        assertEquals("first", event.events[0].payload["text"]?.jsonPrimitive?.content)
        assertEquals("bash", event.events[1].payload["name"]?.jsonPrimitive?.content)
    }

    @Test
    fun `session frame parses`() {
        val payload = """
            {"type":"session","session_id":"s1","instance_id":"i1","name":"llm-dock",
             "cwd":"/repo","model":"mistral/small","thinking_level":"high",
             "first_seen":1000,"last_seen":2000,"ended_at":null,"end_reason":null,
             "live":true,"state":"working","context_percent":22.5}
        """.trimIndent()

        val event = parsePiSessionStreamFrame(payload) as PiSessionStreamEvent.Session
        assertEquals("s1", event.session.sessionId)
        assertEquals("i1", event.session.instanceId)
        assertEquals("mistral/small", event.session.model)
        assertEquals(22.5, event.session.contextPercent!!, 0.0)
    }

    @Test
    fun `lagged parses after`() {
        assertEquals(42L, (parsePiSessionStreamFrame("""{"type":"lagged","after":42}""") as PiSessionStreamEvent.Lagged).after)
    }

    @Test
    fun `unknown type is Unknown`() {
        val payload = """{"type":"future","events":[]}"""
        assertEquals(PiSessionStreamEvent.Unknown(payload), parsePiSessionStreamFrame(payload))
    }

    @Test
    fun `malformed json is Unknown`() {
        assertEquals(PiSessionStreamEvent.Unknown("not json"), parsePiSessionStreamFrame("not json"))
    }
}
