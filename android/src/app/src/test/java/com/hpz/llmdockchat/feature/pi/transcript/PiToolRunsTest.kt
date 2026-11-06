package com.hpz.llmdockchat.feature.pi.transcript

import org.junit.Assert.assertEquals
import org.junit.Test

class PiToolRunsTest {
    private fun tool(id: String) = PiItem.Tool("t$id", id, "bash", null, null, ToolStatus.DONE, null, false, 0)
    private fun assistant(id: String, text: String, streaming: Boolean = false) =
        PiItem.Assistant("a$id", text, "", streaming, null, null, null, 0)
    private fun user(id: String) = PiItem.User("u$id", "hi", 0, false, 0)
    private fun kinds(out: List<PiDisplayItem>) = out.map {
        when (it) {
            is PiDisplayItem.ToolGroup -> "group:${it.tools.size}"
            is PiDisplayItem.Single -> it.item.id
        }
    }

    @Test
    fun `consecutive tools form one group`() {
        val out = groupToolRuns(listOf(user("1"), tool("1"), tool("2"), assistant("1", "done")))
        assertEquals(listOf("u1", "group:2", "a1"), kinds(out))
        assertEquals("gt1", out[1].id)
    }

    @Test
    fun `empty assistant turns between tools are absorbed`() {
        val out = groupToolRuns(listOf(tool("1"), assistant("1", " "), tool("2"), assistant("2", "answer")))
        assertEquals(listOf("group:2", "a2"), kinds(out))
    }

    @Test
    fun `assistant text splits groups`() {
        assertEquals(listOf("group:1", "a1", "group:1"), kinds(groupToolRuns(listOf(tool("1"), assistant("1", "looking"), tool("2")))))
    }

    @Test
    fun `streaming assistant is not absorbed`() {
        assertEquals(listOf("group:1", "a1"), kinds(groupToolRuns(listOf(tool("1"), assistant("1", "", streaming = true)))))
    }

    @Test
    fun `empty assistant before the first tool stays`() {
        assertEquals(listOf("a1", "group:1"), kinds(groupToolRuns(listOf(assistant("1", ""), tool("1")))))
    }

    @Test
    fun `json args become key value pairs`() {
        assertEquals("account=me · limit=5 · flags=[\"a\"]", argsSummary("{\"account\":\"me\",\"limit\":5,\"flags\":[\"a\"]}"))
    }

    @Test
    fun `non json args stay raw and flattened`() {
        assertEquals("{\"command\":\"ls -la", argsSummary("{\"command\":\"ls\n -la"))
    }

    @Test
    fun `null is empty and long text is cut`() {
        assertEquals("", argsSummary(null))
        assertEquals(161, argsSummary("x".repeat(200)).length)
    }

    @Test
    fun `three or fewer tools are all shown`() {
        val tools = listOf(tool("1"), tool("2"), tool("3"))
        assertEquals(VisibleTools(tools, 0), visibleTools(tools, expanded = false))
    }

    @Test
    fun `more than three shows the first three and counts the rest`() {
        val tools = (1..5).map { tool("$it") }
        assertEquals(VisibleTools(tools.take(3), 2), visibleTools(tools, expanded = false))
        assertEquals("2 more…", moreLabel(2))
    }

    @Test
    fun `expanded shows every tool`() {
        val tools = (1..5).map { tool("$it") }
        assertEquals(VisibleTools(tools, 0), visibleTools(tools, expanded = true))
    }
}
