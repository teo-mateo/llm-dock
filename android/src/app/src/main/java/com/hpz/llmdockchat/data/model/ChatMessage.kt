package com.hpz.llmdockchat.data.model

/** Who wrote a turn. Anything the server sends that is neither user nor assistant is [OTHER]. */
enum class MessageRole { USER, ASSISTANT, OTHER }

fun parseMessageRole(raw: String): MessageRole = when (raw) {
    "user" -> MessageRole.USER
    "assistant" -> MessageRole.ASSISTANT
    else -> MessageRole.OTHER
}

/** A tool call as persisted on a message, or as assembled live from the stream. */
data class ToolCallRecord(
    val name: String,
    val arguments: String,
    val result: String?,
    val serverId: String?,
) {
    val isRunning: Boolean get() = result == null
}

/** `{kind, snippet, description}` — surfaced quietly on the turn (F04-R5). */
data class ParseWarning(
    val kind: String?,
    val description: String?,
    val snippet: String?,
) {
    val displayText: String
        get() = description?.takeIf { it.isNotBlank() }
            ?: kind?.takeIf { it.isNotBlank() }
            ?: "The model emitted a malformed tool call."
}

/**
 * A tool-produced artifact (F05-R6/R8) — `svg`, `image`, `html` or `code`.
 * Persisted ones arrive out of band, in `GET /api/chat/conversations/<id>`'s
 * top-level `artifacts: {message_id: [...]}` map (`chat/db.py:get_artifacts_for_conversation`),
 * not nested on the message itself; the mapper folds them in by id.
 */
data class ArtifactRecord(
    val type: String,
    val title: String?,
    val content: String,
    val language: String?,
)

/**
 * A message as the **server** has it. The client never fabricates one of these
 * from streamed text — that is Architecture D3, and it is what keeps a
 * cancelled run from inventing an assistant turn that does not exist.
 */
data class ChatMessage(
    val id: String,
    val role: MessageRole,
    val content: String,
    val reasoning: String?,
    val modelService: String?,
    val images: List<String>,
    val seq: Int,
    val createdAt: String?,
    val toolCalls: List<ToolCallRecord>,
    val parseWarning: ParseWarning?,
    val error: String?,
    val artifacts: List<ArtifactRecord> = emptyList(),
)

/** The most recent run on a thread, whatever its status. */
data class LastRun(val id: String, val status: String, val error: String?) {
    val hasFailed: Boolean get() = status == "failed"
}

/** `GET /api/chat/conversations/<id>` — the whole thread. */
data class ConversationDetail(
    val id: String,
    val title: String,
    val modelRef: ModelRef,
    val messages: List<ChatMessage>,
    val activeRun: ActiveRun?,
    val lastRun: LastRun?,
    val updatedAt: String?,
    /**
     * The enabled MCP server ids (F08). Read-only here — `mcp_servers` on the
     * wire is a read-only array; changing it goes through
     * `ConversationsRepository.setMcpServers`'s `mcp_servers_json` PUT
     * (Architecture D6), never a write to this field.
     */
    val mcpServers: List<String> = emptyList(),
) {
    val isGenerating: Boolean
        get() = activeRun != null && activeRun.status in GENERATING_STATUSES

    private companion object {
        val GENERATING_STATUSES = setOf("queued", "running")
    }
}
