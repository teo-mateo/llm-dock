package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey

const val PI_NO_PROJECT = "other"

enum class PiSection { LIVE, ENDED }

fun piProjectKey(section: PiSection, project: String): String =
    "${section.name.lowercase()}:$project"

fun piProjectExpanded(
    section: PiSection,
    project: String,
    toggles: Map<String, Boolean>,
): Boolean = toggles[piProjectKey(section, project)] ?: (section == PiSection.LIVE)

data class PiSessionNode(val session: PiSession, val children: List<PiSession>)

data class PiProjectGroup(val project: String, val roots: List<PiSessionNode>)

data class PiSessionTree(val live: List<PiProjectGroup>, val ended: List<PiProjectGroup>) {
    val isEmpty: Boolean
        get() = live.isEmpty() && ended.isEmpty()
}

fun buildPiSessionTree(sessions: List<PiSession>): PiSessionTree {
    val bySessionId = sessions.groupBy { it.key.sessionId }
    val parentOf = sessions.associate { it.key to parentRow(it, bySessionId) }
    val roots = mutableListOf<PiSession>()
    val childrenByRoot = mutableMapOf<PiSessionKey, MutableList<PiSession>>()
    for (session in sessions) {
        val root = topAncestor(session, parentOf)
        if (root == null) {
            roots += session
        } else {
            childrenByRoot.getOrPut(root.key) { mutableListOf() } += session
        }
    }
    val nodes = roots.map { root ->
        PiSessionNode(root, childrenByRoot[root.key].orEmpty().sortedWith(childOrder))
    }
    val (live, ended) = nodes.partition { it.session.live }
    return PiSessionTree(groups(live), groups(ended))
}

private val childOrder = compareBy<PiSession> { it.firstSeen }
    .thenBy { it.key.sessionId }
    .thenBy { it.key.instanceId }

private val nodeOrder = compareByDescending<PiSessionNode> { it.session.lastSeen }
    .thenBy { it.session.key.sessionId }
    .thenBy { it.session.key.instanceId }

private val parentOrder = compareByDescending<PiSession> { it.live }
    .thenByDescending { it.lastSeen }
    .thenByDescending { it.firstSeen }
    .thenBy { it.key.instanceId }

private fun parentRow(session: PiSession, bySessionId: Map<String, List<PiSession>>): PiSession? {
    val parentId = session.parentSessionId ?: return null
    return bySessionId[parentId]
        ?.filterNot { it.key == session.key }
        ?.sortedWith(parentOrder)
        ?.firstOrNull()
}

private fun topAncestor(
    session: PiSession,
    parentOf: Map<PiSessionKey, PiSession?>,
): PiSession? {
    val visited = mutableSetOf(session.key)
    var current = parentOf[session.key] ?: return null
    while (true) {
        if (!visited.add(current.key)) return null
        current = parentOf[current.key] ?: return current
    }
}

private fun groups(nodes: List<PiSessionNode>): List<PiProjectGroup> =
    nodes.groupBy { it.session.project ?: PI_NO_PROJECT }
        .map { (project, group) -> PiProjectGroup(project, group.sortedWith(nodeOrder)) }
        .sortedWith(
            compareByDescending<PiProjectGroup> { group -> group.roots.maxOf { it.session.lastSeen } }
                .thenBy { it.project },
        )
