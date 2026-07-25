package com.hpz.llmdockchat.feature.thread

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.Image
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.ChatMessage
import com.hpz.llmdockchat.data.model.MessageRole
import com.hpz.llmdockchat.data.model.ParseWarning
import com.hpz.llmdockchat.data.model.ToolCallRecord

/**
 * The mockup's split (screen 04): the user's own words in mono, the model's in
 * serif, so it is obvious who is talking without an avatar. Markdown rendering
 * is F05 — this shows the text as it came.
 */
@Composable
fun MessageBubble(message: ChatMessage, modifier: Modifier = Modifier) {
    when (message.role) {
        MessageRole.USER -> UserBubble(message, modifier)
        else -> AssistantBubble(
            content = message.content,
            reasoning = message.reasoning,
            toolCalls = message.toolCalls,
            parseWarning = message.parseWarning,
            error = message.error,
            modifier = modifier,
        )
    }
}

@Composable
private fun UserBubble(message: ChatMessage, modifier: Modifier = Modifier) {
    val colors = LlmTheme.colors
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp),
        horizontalAlignment = Alignment.End,
    ) {
        if (message.images.isNotEmpty()) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(bottom = 6.dp)) {
                message.images.forEach { ImageThumbnail(it, size = 84.dp) }
            }
        }
        if (message.content.isNotBlank()) {
            Box(
                Modifier
                    .clip(RoundedCornerShape(14.dp))
                    .background(colors.surfaceElevated)
                    .padding(horizontal = 14.dp, vertical = 10.dp),
            ) {
                Text(
                    message.content,
                    color = colors.fg,
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}

/**
 * Shared by a persisted assistant turn and the live one, so a streamed answer
 * and the saved message it becomes look identical — no visual jump when
 * `message_saved` lands and D3 swaps one for the other.
 */
@Composable
fun AssistantBubble(
    content: String,
    reasoning: String?,
    toolCalls: List<ToolCallRecord>,
    parseWarning: ParseWarning?,
    error: String?,
    modifier: Modifier = Modifier,
    trailing: @Composable (() -> Unit)? = null,
) {
    val colors = LlmTheme.colors
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (!reasoning.isNullOrBlank()) ReasoningBlock(reasoning)
        toolCalls.forEach { ToolCallCard(it) }
        parseWarning?.let { ParseWarningChip(it) }
        if (content.isNotBlank()) {
            Text(
                content,
                color = colors.fg,
                fontFamily = FontFamily.Serif,
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.testTag("assistant_text"),
            )
        }
        error?.let { ErrorNote(it) }
        trailing?.invoke()
    }
}

/**
 * F04-R4 — collapsed by default, and never mixed into the answer body. Absent
 * entirely when the model emitted no reasoning, so a non-thinking model shows
 * no empty block.
 */
@Composable
private fun ReasoningBlock(reasoning: String) {
    val colors = LlmTheme.colors
    var expanded by remember { mutableStateOf(false) }
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(colors.sunken)
            .clickable { expanded = !expanded }
            .padding(horizontal = 12.dp, vertical = 9.dp)
            .testTag("reasoning_block"),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(if (expanded) "▾" else "▸", color = colors.subtle, style = MaterialTheme.typography.labelMedium)
            Text(
                "Reasoning",
                color = colors.muted,
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.weight(1f),
            )
            Text("${reasoning.length} chars", color = colors.subtle, style = MaterialTheme.typography.labelSmall)
        }
        if (expanded) {
            Text(
                reasoning,
                color = colors.muted,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.testTag("reasoning_text"),
            )
        }
    }
}

/** F04-R5 — one line while running, updated in place when the result arrives. */
@Composable
private fun ToolCallCard(call: ToolCallRecord) = ToolCallCard(
    name = call.name,
    serverId = call.serverId,
    arguments = call.arguments,
    result = call.result,
)

@Composable
fun ToolCallCard(call: StreamingToolCall) = ToolCallCard(
    name = call.name,
    serverId = call.serverId,
    arguments = call.arguments,
    result = call.result,
)

@Composable
private fun ToolCallCard(name: String, serverId: String?, arguments: String?, result: String?) {
    val colors = LlmTheme.colors
    var expanded by remember { mutableStateOf(false) }
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(colors.sunken)
            .clickable { expanded = !expanded }
            .padding(horizontal = 12.dp, vertical = 9.dp)
            .testTag("tool_call_$name"),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(
                Modifier
                    .size(7.dp)
                    .background(if (result == null) colors.amber else colors.green, CircleShape),
            )
            Text(
                serverId?.let { "$it · $name" } ?: name,
                color = colors.muted,
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.weight(1f),
            )
            Text(if (expanded) "▾" else "▸", color = colors.subtle, style = MaterialTheme.typography.labelMedium)
        }
        if (expanded) {
            MonoBlock("arguments", arguments.orEmpty().ifBlank { "—" })
            MonoBlock("result", result ?: "running…")
        }
    }
}

@Composable
private fun MonoBlock(label: String, value: String) {
    val colors = LlmTheme.colors
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, color = colors.subtle, style = MaterialTheme.typography.labelSmall)
        Box(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())) {
            Text(value, color = colors.fg, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
        }
    }
}

/** Quiet, not a modal (F04-R5's fourth criterion). */
@Composable
fun ParseWarningChip(warning: ParseWarning) {
    val colors = LlmTheme.colors
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(colors.amber.copy(alpha = 0.14f))
            .padding(horizontal = 10.dp, vertical = 7.dp)
            .testTag("parse_warning"),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("⚠", color = colors.amber, style = MaterialTheme.typography.labelLarge)
        Text(warning.displayText, color = colors.amber, style = MaterialTheme.typography.labelMedium)
    }
}

/** A failed run's message, attached to the turn it belongs to (F04-R8). */
@Composable
fun ErrorNote(message: String) {
    val colors = LlmTheme.colors
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(colors.red.copy(alpha = 0.13f))
            .padding(horizontal = 10.dp, vertical = 8.dp)
            .testTag("run_error"),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("✕", color = colors.red, style = MaterialTheme.typography.labelLarge)
        Text(message, color = colors.red, style = MaterialTheme.typography.bodySmall)
    }
}

/**
 * Decodes a `data:image/…;base64,…` URL — the same encoding the web composer
 * sends. Done here rather than with an image loader because the bytes are
 * already in the payload; there is nothing to fetch.
 */
@Composable
fun ImageThumbnail(dataUrl: String, size: androidx.compose.ui.unit.Dp, onRemove: (() -> Unit)? = null) {
    val colors = LlmTheme.colors
    val bitmap = remember(dataUrl) { decodeDataUrl(dataUrl) }
    Box(Modifier.size(size)) {
        if (bitmap != null) {
            Image(
                bitmap = bitmap.asImageBitmap(),
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.size(size).clip(RoundedCornerShape(10.dp)),
            )
        } else {
            Box(
                Modifier
                    .size(size)
                    .clip(RoundedCornerShape(10.dp))
                    .background(colors.surfaceElevated),
                contentAlignment = Alignment.Center,
            ) {
                Text("img", color = colors.subtle, style = MaterialTheme.typography.labelSmall)
            }
        }
        if (onRemove != null) {
            Box(
                Modifier
                    .align(Alignment.TopEnd)
                    .size(22.dp)
                    .clip(CircleShape)
                    .background(colors.surfaceElevated)
                    .clickable(onClick = onRemove)
                    .testTag("attachment_remove"),
                contentAlignment = Alignment.Center,
            ) {
                Text("✕", color = colors.fg, style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}
