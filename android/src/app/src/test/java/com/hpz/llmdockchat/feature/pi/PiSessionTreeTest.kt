package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.data.model.PiState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PiSessionTreeTest {

    private fun session(
        id: String,
        instance: String = "i1",
        live: Boolean = true,
        parent: String? = null,
        parentInstance: String? = "i1",
        project: String? = "repo",
        firstSeen: Long = 0,
        lastSeen: Long = 0,
    ) = PiSession(
        key = PiSessionKey(id, instance),
        name = null,
        cwd = "/repo",
        model = null,
        thinkingLevel = null,
        firstSeen = firstSeen,
        lastSeen = lastSeen,
        endedAt = if (live) null else 1,
        endReason = null,
        live = live,
        state = if (live) PiState.IDLE else PiState.ENDED,
        contextPercent = null,
        parentSessionId = parent,
        parentInstanceId = if (parent == null) null else parentInstance,
        project = project,
    )

    private fun ids(groups: List<PiProjectGroup>): List<String> =
        groups.flatMap { group -> group.roots.flatMap { listOf(it.session.key.sessionId) + it.children.map { c -> c.key.sessionId } } }

    private fun childIds(groups: List<PiProjectGroup>, project: String): List<String> =
        groups.first { it.project == project }.roots.flatMap { node -> node.children.map { it.key.sessionId } }

    @Test
    fun `children nest under their parent`() {
        val tree = buildPiSessionTree(
            listOf(
                session("root", firstSeen = 1, lastSeen = 10),
                session("run-b", parent = "root", firstSeen = 5, lastSeen = 6),
                session("run-a", parent = "root", firstSeen = 3, lastSeen = 4),
            ),
        )

        assertEquals(listOf("root"), tree.live.flatMap { g -> g.roots.map { it.session.key.sessionId } })
        assertEquals(listOf("run-a", "run-b"), childIds(tree.live, "repo"))
    }

    @Test
    fun `an orphan is promoted to top level`() {
        val tree = buildPiSessionTree(
            listOf(session("root"), session("run", parent = "gone")),
        )

        assertEquals(listOf("root", "run"), ids(tree.live).sorted())
        assertTrue(tree.live.all { group -> group.roots.size == 2 })
    }

    @Test
    fun `a grandchild is flattened under the root`() {
        val tree = buildPiSessionTree(
            listOf(
                session("root", firstSeen = 1),
                session("child", parent = "root", firstSeen = 2),
                session("grandchild", parent = "child", firstSeen = 3),
            ),
        )

        assertEquals(listOf("root"), tree.live.flatMap { g -> g.roots.map { it.session.key.sessionId } })
        assertEquals(listOf("child", "grandchild"), childIds(tree.live, "repo"))
    }

    @Test
    fun `a child follows its parent into the ended section`() {
        val tree = buildPiSessionTree(
            listOf(
                session("root", live = false),
                session("run", parent = "root", live = true),
            ),
        )

        assertTrue(tree.live.isEmpty())
        assertEquals(listOf("root", "run"), ids(tree.ended))
    }

    @Test
    fun `a child follows its parent into the live section`() {
        val tree = buildPiSessionTree(
            listOf(
                session("root", live = true),
                session("run", parent = "root", live = false),
            ),
        )

        assertEquals(listOf("root", "run"), ids(tree.live))
        assertTrue(tree.ended.isEmpty())
    }

    @Test
    fun `a cycle promotes every member to top level`() {
        val tree = buildPiSessionTree(
            listOf(
                session("a", parent = "b"),
                session("b", parent = "a"),
                session("c", parent = "a"),
            ),
        )

        assertEquals(listOf("a", "b", "c"), tree.live.flatMap { g -> g.roots.map { it.session.key.sessionId } }.sorted())
        assertTrue(tree.live.all { group -> group.roots.all { it.children.isEmpty() } })
    }

    @Test
    fun `a session cannot be its own parent`() {
        val tree = buildPiSessionTree(listOf(session("a", parent = "a")))

        assertEquals(listOf("a"), ids(tree.live))
        assertTrue(tree.live.single().roots.single().children.isEmpty())
    }

    @Test
    fun `a parent without a resolved instance is promoted to top level`() {
        val tree = buildPiSessionTree(
            listOf(
                session("root"),
                session("run", parent = "root", parentInstance = null),
            ),
        )

        assertEquals(listOf("root", "run"), ids(tree.live).sorted())
        assertTrue(tree.live.single().roots.all { it.children.isEmpty() })
    }

    @Test
    fun `a resolved parent instance links the row even when a sibling row shares the session id`() {
        val tree = buildPiSessionTree(
            listOf(
                session("root", instance = "old", live = false, lastSeen = 1),
                session("root", instance = "new", live = true, lastSeen = 2),
                session("run", parent = "root", parentInstance = "new"),
            ),
        )

        val liveRoot = tree.live.single().roots.single()
        assertEquals("new", liveRoot.session.key.instanceId)
        assertEquals(listOf("run"), liveRoot.children.map { it.key.sessionId })
        assertEquals(listOf("old"), tree.ended.single().roots.map { it.session.key.instanceId })
    }

    @Test
    fun `sessions without a project share the other group`() {
        val tree = buildPiSessionTree(
            listOf(session("a", project = null), session("b", project = null)),
        )

        assertEquals(listOf(PI_NO_PROJECT), tree.live.map { it.project })
        assertEquals(2, tree.live.single().roots.size)
    }

    @Test
    fun `groups and roots are ordered by recency`() {
        val tree = buildPiSessionTree(
            listOf(
                session("old", project = "a/b", lastSeen = 10),
                session("new", project = "c/d", lastSeen = 30),
                session("mid", project = "a/b", lastSeen = 20),
            ),
        )

        assertEquals(listOf("c/d", "a/b"), tree.live.map { it.project })
        assertEquals(listOf("mid", "old"), tree.live[1].roots.map { it.session.key.sessionId })
    }

    @Test
    fun `input order does not change the tree`() {
        val sessions = listOf(
            session("root", firstSeen = 1, lastSeen = 10),
            session("run", parent = "root", firstSeen = 2),
            session("other", project = "x/y", lastSeen = 5),
        )

        assertEquals(buildPiSessionTree(sessions), buildPiSessionTree(sessions.reversed()))
    }

    @Test
    fun `empty input gives an empty tree`() {
        val tree = buildPiSessionTree(emptyList())

        assertTrue(tree.isEmpty)
        assertTrue(tree.live.isEmpty())
        assertTrue(tree.ended.isEmpty())
    }

    @Test
    fun `live groups start expanded and ended groups start collapsed`() {
        val toggles = emptyMap<String, Boolean>()

        assertTrue(piProjectExpanded(PiSection.LIVE, "a/b", toggles))
        assertFalse(piProjectExpanded(PiSection.ENDED, "a/b", toggles))
    }

    @Test
    fun `a toggle overrides the default for its section only`() {
        val toggles = mapOf(
            piProjectKey(PiSection.LIVE, "a/b") to false,
            piProjectKey(PiSection.ENDED, "c/d") to true,
        )

        assertFalse(piProjectExpanded(PiSection.LIVE, "a/b", toggles))
        assertTrue(piProjectExpanded(PiSection.LIVE, "x/y", toggles))
        assertTrue(piProjectExpanded(PiSection.ENDED, "c/d", toggles))
        assertFalse(piProjectExpanded(PiSection.ENDED, "a/b", toggles))
    }
}
