package com.hpz.llmdockchat.core.attachment

/**
 * The staged images a conversation carries between a pick and a send. The
 * composer reads them back when it opens, removes one when the user does, and
 * clears them when the turn is sent or the thread is left — nothing else about
 * where they are stored belongs to it.
 */
interface ConversationAttachments {
    suspend fun attachments(conversationId: String): List<String>

    fun removeAttachment(conversationId: String, index: Int)

    fun clear(conversationId: String)
}

/**
 * One prepared turn owed to a conversation, written before the thread opens and
 * spent by its first read. A claim is not attachment storage: it is a message
 * that has not been sent yet, which is why it is its own contract.
 */
interface AutoSendClaimStore {
    suspend fun takeAutoSend(conversationId: String): String?
}
