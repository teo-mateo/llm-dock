package com.hpz.llmdockchat.feature.thread

import com.hpz.llmdockchat.data.model.ArtifactRecord
import com.hpz.llmdockchat.data.model.ChatMessage
import com.hpz.llmdockchat.data.model.ConversationDetail
import com.hpz.llmdockchat.data.model.ParseWarning

/** What the user typed, shown before the server has a message id for it. */
data class PendingUserMessage(val content: String, val images: List<String> = emptyList())

/**
 * A tool call being assembled from the stream. `tool_call_pending` gives the
 * name before the arguments exist, `tool_call` fills them in, `tool_result`
 * completes it — the card updates in place rather than a second card appearing
 * (F04-R5).
 */
data class StreamingToolCall(
    val name: String,
    val serverId: String?,
    val arguments: String? = null,
    val result: String? = null,
) {
    val isRunning: Boolean get() = result == null
}

/**
 * The turn currently being generated. **Never** merged into
 * [ThreadState.messages] — see [ThreadState].
 */
data class StreamingTurn(
    /** Null when reattaching to a run this client did not start (F09). */
    val userMessage: PendingUserMessage?,
    val runId: String? = null,
    val content: String = "",
    val reasoning: String = "",
    val toolCalls: List<StreamingToolCall> = emptyList(),
    val parseWarning: ParseWarning? = null,
    /** Frames arrive as they're produced; the panel appears as soon as one has (F05-R6/R8). */
    val artifacts: List<ArtifactRecord> = emptyList(),
    /** Stop has been requested; the server cancels cooperatively, so this lingers a moment. */
    val stopping: Boolean = false,
    /**
     * The run is over, but the refetch that should have replaced this turn with
     * the server's copy failed. The text is held over so the answer does not
     * vanish; it is not a live run, and the next successful load discards it.
     */
    val unconfirmed: Boolean = false,
    /**
     * The run's error, shown on the turn itself when the refetch that would
     * normally surface it through `last_run` could not be made.
     */
    val error: String? = null,
) {
    val hasVisibleOutput: Boolean
        get() = content.isNotEmpty() || reasoning.isNotEmpty() || toolCalls.isNotEmpty()
}

/**
 * Architecture D3 — the one rule the whole feature hangs off.
 *
 * [messages] is what the server has, always. [streaming] is ephemeral and is
 * never appended to it. On any terminal the client drops [streaming] and
 * refetches, so the three outcomes need no special-casing between them:
 *
 * | terminal | what the server has | what is shown after |
 * |---|---|---|
 * | `message_saved` | the assistant message | the saved message |
 * | `{"error": …}` | the partial **plus** the error | the partial, with the error |
 * | cancelled (stream just ends) | nothing | the user's turn alone |
 *
 * Merging streamed text into [messages] would invent an assistant turn after a
 * cancel, miss the error the server attached after a failure, and duplicate
 * text when F09 replays a run the client had already seen.
 */
data class ThreadState(
    val messages: List<ChatMessage> = emptyList(),
    val streaming: StreamingTurn? = null,
)

/**
 * An edit about to be confirmed (F06-R3). [discardCount] is messages
 * **strictly after** [message] — the edited message itself is not discarded,
 * it is replaced in place, matching what `PUT …/messages/<id>` actually does
 * server-side (`DELETE … WHERE seq >= msg.seq`, then a fresh row is inserted
 * for the edit itself).
 */
data class PendingEdit(
    val message: ChatMessage,
    val content: String,
    val images: List<String>,
    val discardCount: Int,
)

sealed interface ThreadUiState {
    data object Loading : ThreadUiState

    data class Failed(val message: String) : ThreadUiState

    data class Loaded(
        val conversation: ConversationDetail,
        val thread: ThreadState,
        val composer: String = "",
        val attachments: List<String> = emptyList(),
        /** The send request is open but no frame has arrived yet. */
        val sending: Boolean = false,
        /** Surfaced once and dismissed — a 409, a failed Stop, an unreadable photo. */
        val actionError: String? = null,
        /** Confirm-before-delete (F06-R2, F00-R9). Null until Delete is tapped in the menu. */
        val pendingDelete: ChatMessage? = null,
        /**
         * The composer is prefilled with this message's text/images and Send
         * now means "edit and resend" (F06-R3). Only ever a user message —
         * the server rejects editing an assistant one.
         */
        val editingMessage: ChatMessage? = null,
        /** Confirm-before-edit-and-resend, holding the exact discard count. */
        val pendingEdit: PendingEdit? = null,
    ) : ThreadUiState {

        /**
         * Either this client is streaming, or the server says a run is live in
         * this thread (started on the desktop, or left running here). Sending
         * during one earns a 409 and a rolled-back user message, so the
         * composer disables instead (F04-R2).
         */
        val runActive: Boolean
            get() = sending ||
                thread.streaming?.unconfirmed == false ||
                conversation.isGenerating

        val canSend: Boolean
            get() = !runActive && (composer.isNotBlank() || attachments.isNotEmpty())

        /**
         * A run that failed — including one that failed while the app was
         * elsewhere, which is why this reads the conversation's `last_run`
         * rather than anything the stream carried (F04-R8).
         */
        val runError: String?
            get() = conversation.lastRun?.takeIf { it.hasFailed }?.error
    }
}
