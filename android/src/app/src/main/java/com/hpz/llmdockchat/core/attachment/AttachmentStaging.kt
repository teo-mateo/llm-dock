package com.hpz.llmdockchat.core.attachment

import com.hpz.llmdockchat.core.prefs.DraftStore

/**
 * Filing staged content into a conversation before its thread opens — what a
 * picker or a new-chat sheet does. The thread's own copy of that content is
 * [ConversationAttachments], which both reads and edits it.
 *
 * Every method reports whether the write landed. A caller that spends its own
 * source record — the pending share, a staged claim — must wait for that result,
 * which is why none of these is fire-and-forget.
 */
interface AttachmentStaging {
    suspend fun appendAttachments(conversationId: String, attachments: List<String>): Result<Unit>

    /** Files the staged share: its text merged into the draft, its images appended. */
    suspend fun reassign(conversationId: String, drafts: DraftStore): Result<Unit>

    /** Files the turn a summarize tap owes the thread, spent by its first read. */
    suspend fun stageForAutoSend(conversationId: String, message: String): Result<Unit>
}
