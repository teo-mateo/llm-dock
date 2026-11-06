package com.hpz.llmdockchat.core.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PiSessionsStreamEventTest {

    @Test
    fun `snapshot parses all sessions`() {
        val payload = """
            {"type":"snapshot","sessions":[
                {"session_id":"s1","instance_id":"i1","name":"llm-dock",
                 "cwd":"/repo","model":"mistral/small","thinking_level":"high",
                 "first_seen":1000,"last_seen":2000,"ended_at":null,"end_reason":null,
                 "live":true,"state":"working","context_percent":22.5},
                {"session_id":"s2","instance_id":"i2","name":null,
                 "cwd":"/android","model":null,"thinking_level":null,
                 "first_seen":500,"last_seen":900,"ended_at":900,"end_reason":"bye",
                 "live":false,"state":null,"context_percent":null}
            ]}
        """.trimIndent()

        val event = parsePiSessionsStreamFrame(payload) as PiSessionsStreamEvent.Snapshot
        assertEquals(2, event.sessions.size)
        assertEquals("s1", event.sessions[0].sessionId)
        assertEquals("mistral/small", event.sessions[0].model)
        assertEquals(22.5, event.sessions[0].contextPercent!!, 0.0)
        assertEquals("bye", event.sessions[1].endReason)
        assertEquals(false, event.sessions[1].live)
    }

    @Test
    fun `session frame parses one`() {
        val payload = """
            {"type":"session","session_id":"s1","instance_id":"i1","name":"llm-dock",
             "cwd":"/repo","model":"mistral/small","thinking_level":"high",
             "first_seen":1000,"last_seen":2000,"ended_at":null,"end_reason":null,
             "live":true,"state":"idle","context_percent":10}
        """.trimIndent()

        val event = parsePiSessionsStreamFrame(payload) as PiSessionsStreamEvent.Session
        assertEquals("s1", event.session.sessionId)
        assertEquals("i1", event.session.instanceId)
        assertEquals("idle", event.session.state)
        assertEquals(10.0, event.session.contextPercent!!, 0.0)
    }

    @Test
    fun `prompts parse from a session frame`() {
        val payload = """
            {"type":"session","session_id":"s1","instance_id":"i1","name":"llm-dock",
             "cwd":"/repo","model":null,"thinking_level":null,
             "first_seen":1000,"last_seen":2000,"ended_at":null,"end_reason":null,
             "live":true,"state":"working","context_percent":null,
             "prompts":[{"prompt_id":"p1","kind":"confirm","title":"Run command?",
                         "message":"rm -r build","options":["Allow","Deny"],
                         "allow_free_text":false,"timeout_ms":30000}]}
        """.trimIndent()

        val event = parsePiSessionsStreamFrame(payload) as PiSessionsStreamEvent.Session
        assertEquals(1, event.session.prompts.size)
        assertEquals("p1", event.session.prompts[0].promptId)
        assertEquals("confirm", event.session.prompts[0].kind)
        assertEquals("Run command?", event.session.prompts[0].title)
    }

    @Test
    fun `a summary without a prompts key and an empty prompts list both mean no open prompts`() {
        val absent = """
            {"type":"session","session_id":"s1","instance_id":"i1","cwd":"/repo",
             "first_seen":1000,"last_seen":2000,"live":true,"state":"idle"}
        """.trimIndent()
        val empty = """
            {"type":"session","session_id":"s1","instance_id":"i1","cwd":"/repo",
             "first_seen":1000,"last_seen":2000,"live":true,"state":"idle","prompts":[]}
        """.trimIndent()

        assertEquals(
            emptyList<Any>(),
            (parsePiSessionsStreamFrame(absent) as PiSessionsStreamEvent.Session).session.prompts,
        )
        assertEquals(
            emptyList<Any>(),
            (parsePiSessionsStreamFrame(empty) as PiSessionsStreamEvent.Session).session.prompts,
        )
    }

    @Test
    fun `lagged parses`() {
        assertEquals(
            PiSessionsStreamEvent.Lagged,
            parsePiSessionsStreamFrame("""{"type":"lagged"}"""),
        )
    }

    @Test
    fun `unknown type is Unknown`() {
        val payload = """{"type":"future","sessions":[]}"""
        assertEquals(PiSessionsStreamEvent.Unknown(payload), parsePiSessionsStreamFrame(payload))
    }

    @Test
    fun `malformed json is Unknown`() {
        assertEquals(
            PiSessionsStreamEvent.Unknown("not json"),
            parsePiSessionsStreamFrame("not json"),
        )
    }

    @Test
    fun `missing nullable fields map to null`() {
        val payload = """
            {"type":"session","session_id":"s1","instance_id":"i1",
             "cwd":"/repo","first_seen":1,"last_seen":2,"live":true}
        """.trimIndent()

        val session = (parsePiSessionsStreamFrame(payload) as PiSessionsStreamEvent.Session).session
        assertNull(session.name)
        assertNull(session.model)
        assertNull(session.thinkingLevel)
        assertNull(session.endedAt)
        assertNull(session.endReason)
        assertNull(session.state)
        assertNull(session.contextPercent)
        assertTrue(session.live)
    }
}
