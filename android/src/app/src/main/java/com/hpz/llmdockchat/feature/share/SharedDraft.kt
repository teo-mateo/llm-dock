package com.hpz.llmdockchat.feature.share

import kotlinx.serialization.Serializable

/**
 * What a share intent turned into, staged for the user to adapt before sending
 * (F14-R3). [text] is composer text — the shared text/link itself, or a text
 * file inlined as a fenced code block (web parity, `ChatInput.jsx`).
 * [attachments] are `data:image/jpeg;base64,…` URLs through the same pipeline
 * as F04-R9. [error] is set when the share was unsupported (PDF, binary) —
 * nothing is staged, the picker shows the reason.
 */
@Serializable
data class StagedShare(
    val text: String = "",
    val attachments: List<String> = emptyList(),
    val error: String? = null,
) {
    val hasContent: Boolean get() = text.isNotBlank() || attachments.isNotEmpty()
    val isEmpty: Boolean get() = !hasContent && error == null
}

/**
 * What a share intent *is*, classified from its raw extras — pure, so the
 * rules are JVM-testable without an `Intent`. Reading the stream itself is
 * I/O and happens later, in the stager.
 */
sealed interface SharedKind {
    /** `text/plain` + `EXTRA_TEXT` — lands in the composer. */
    data class Text(val text: String) : SharedKind

    /** An image share (`image/…` + `EXTRA_STREAM`) — lands as an attachment. */
    data object Image : SharedKind

    /** A text/code file — read and inlined as a fenced block (web parity). */
    data class TextFile(val name: String) : SharedKind

    /** PDF/binary/unknown — nothing staged, the reason shown on the picker. */
    data class Unsupported(val reason: String) : SharedKind
}

/**
 * Classifies a share intent (F14). The precedence rules are F14's decision
 * 4.7: `EXTRA_TEXT` wins for `text/plain` (apps like WhatsApp share a link as
 * text *and* a preview image — the link is what the user asked to send);
 * `EXTRA_STREAM` wins for an image share; a `text/plain` share with only a
 * stream is a text file.
 */
object SharedKindParser {
    const val ACTION_SEND = "android.intent.action.SEND"

    /** Cap per-file inlined text — the web's `MAX_INLINE_BYTES` (`ChatInput.jsx`). */
    const val MAX_INLINE_BYTES = 512 * 1024

    /** `ChatInput.jsx`'s `ALLOWED_EXT`, plus the code MIME types it accepts. */
    private val CODE_MIME_TYPES = setOf(
        "application/json",
        "application/x-python", "text/x-python",
        "text/x-java", "text/x-sh", "application/x-sh",
        "application/javascript", "text/javascript",
        "text/x-c", "text/x-c++", "text/x-ruby", "text/x-go",
    )

    private val IMAGE_EXTENSIONS = setOf("jpg", "jpeg", "png", "gif", "webp", "bmp", "heic", "heif")

    /** `ChatInput.jsx`'s `ALLOWED_EXT` verbatim. */
    private val TEXT_EXTENSIONS = setOf(
        "txt", "md", "markdown", "json", "csv", "tsv", "log",
        "js", "jsx", "ts", "tsx", "py", "rb", "go", "rs", "java", "c", "h",
        "cpp", "cc", "hpp", "cs", "php", "swift", "kt", "sh", "bash", "zsh",
        "sql", "html", "css", "scss", "yml", "yaml", "toml", "ini", "xml",
    )

    fun classify(
        action: String,
        mimeType: String?,
        text: String?,
        title: String?,
        subject: String?,
        hasStream: Boolean,
        streamName: String?,
    ): SharedKind {
        if (action != ACTION_SEND) return SharedKind.Unsupported("Not a share intent")
        val mime = mimeType?.lowercase()
        return when {
            mime == "text/plain" && !text.isNullOrBlank() ->
                SharedKind.Text(foldTitle(text, title, subject))
            mime?.startsWith("image/") == true -> SharedKind.Image
            mime == "text/plain" && hasStream -> SharedKind.TextFile(streamName ?: "file.txt")
            mime?.startsWith("text/") == true -> SharedKind.TextFile(streamName ?: "file.txt")
            mime == "application/json" -> SharedKind.TextFile(streamName ?: "file.txt")
            mime != null && mime in CODE_MIME_TYPES -> SharedKind.TextFile(streamName ?: "file.txt")
            mime == "application/pdf" -> SharedKind.Unsupported("PDFs can't be shared into a chat")
            mime == "application/octet-stream" -> SharedKind.Unsupported("Binary files can't be shared into a chat")
            mime == null || mime == "*/*" -> sniff(streamName)
            else -> SharedKind.Unsupported("This file type can't be shared into a chat")
        }
    }

    /**
     * Decision 4.7 — a bare-link share folds `EXTRA_TITLE`/`EXTRA_SUBJECT` in
     * so the URL is not sent with no context; anything else is left untouched.
     */
    private fun foldTitle(text: String, title: String?, subject: String?): String {
        if (!isBareLink(text)) return text
        val extra = listOfNotNull(title, subject).firstOrNull { it.isNotBlank() } ?: return text
        return "$text\n\n$extra"
    }

    private fun isBareLink(text: String): Boolean = text.trim().matches(Regex("https?://\\S+"))

    private fun sniff(name: String?): SharedKind {
        val ext = name?.substringAfterLast('.', "")?.lowercase().orEmpty()
        return when {
            ext in IMAGE_EXTENSIONS -> SharedKind.Image
            ext in TEXT_EXTENSIONS -> SharedKind.TextFile(name ?: "file.txt")
            else -> SharedKind.Unsupported("This file type can't be shared into a chat")
        }
    }
}

/**
 * Renders a text file the way the web does (`ChatInput.jsx`'s `buildMessage`):
 * `**Attached file: \`name\`**` plus a fenced code block, truncated to
 * [SharedKindParser.MAX_INLINE_BYTES] with the same visible marker. The fence
 * is [pickFence]'d — at least three backticks, one more than the longest run
 * in the content — so content containing backticks never breaks the fence.
 */
object SharedInlineFormatter {
    fun inlineFile(name: String, content: String): String {
        val truncated = content.length > SharedKindParser.MAX_INLINE_BYTES
        val capped = if (truncated) content.take(SharedKindParser.MAX_INLINE_BYTES) else content
        val note = if (truncated) " (truncated to ${SharedKindParser.MAX_INLINE_BYTES} bytes)" else ""
        val lang = langHint(name)
        val fence = pickFence(capped)
        return "**Attached file: `$name`**$note\n\n$fence$lang\n$capped\n$fence"
    }

    private fun langHint(name: String): String {
        val ext = name.substringAfterLast('.', "").lowercase()
        if (ext.isEmpty()) return ""
        return if (ext == "md" || ext == "markdown") "markdown" else ext
    }

    fun pickFence(content: String): String {
        var longest = 0
        for (run in Regex("`+").findAll(content)) {
            if (run.value.length > longest) longest = run.value.length
        }
        return "`".repeat(maxOf(3, longest + 1))
    }
}
