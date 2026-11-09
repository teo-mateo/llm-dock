package com.hpz.llmdockchat.feature.pi.tools

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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.icons.AppIcons
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import com.hpz.llmdockchat.feature.pi.transcript.tools.ToolImage
import com.hpz.llmdockchat.feature.pi.transcript.tools.ToolResult
import com.hpz.llmdockchat.feature.pi.transcript.tools.byteSize
import com.hpz.llmdockchat.feature.pi.transcript.tools.parseToolArgs
import com.hpz.llmdockchat.feature.pi.transcript.tools.parseToolResult
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

private const val MAX_LINES = 20

@Composable
internal fun GenericToolBody(item: PiItem.Tool) {
    val colors = LlmTheme.colors
    var raw by rememberSaveable(item.id) { mutableStateOf(false) }
    val args = remember(item.args) { parseToolArgs(item.args) }
    val result = remember(item.output) { parseToolResult(item.output) }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (item.args != null || item.output != null) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                Text(
                    if (raw) "Formatted" else "Raw",
                    color = colors.accent,
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.clickable { raw = !raw }.testTag("pi_tool_raw_toggle"),
                )
            }
        }
        if (raw) RawToolBody(item) else FormattedToolBody(item, args, result)
        if (item.truncated) {
            Text("output truncated by pi-remote", color = colors.amber, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun FormattedToolBody(item: PiItem.Tool, args: JsonObject?, result: ToolResult?) {
    val colors = LlmTheme.colors
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        when {
            args != null && args.isNotEmpty() -> args.entries.forEach { (key, value) -> ArgRow(item.id, key, value) }
            item.args != null -> CappedText(item.id, "args", item.args, colors.muted, "pi_tool_args_toggle")
        }
        if (result != null) {
            val error = result.isError || item.status == ToolStatus.ERROR
            if (result.text.isNotEmpty()) {
                CappedText(item.id, "result", result.text, if (error) colors.red else colors.muted, "pi_tool_output_toggle")
            } else if (result.images.isEmpty() && item.output != null) {
                CappedText(item.id, "result", item.output, if (error) colors.red else colors.muted, "pi_tool_output_toggle")
            }
            result.images.forEach { image ->
                Text(
                    imageLabel(image),
                    color = colors.muted,
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

@Composable
private fun ArgRow(itemId: String, key: String, value: JsonElement) {
    val colors = LlmTheme.colors
    val text = if (value is JsonPrimitive && value.isString) value.content else value.toString()
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(key, color = colors.muted, style = MaterialTheme.typography.labelSmall)
        CappedText(itemId, "arg_$key", text, colors.fg, "pi_tool_arg_${key}_toggle")
    }
}

@Composable
private fun RawToolBody(item: PiItem.Tool) {
    val colors = LlmTheme.colors
    val args = item.args
    val output = item.output
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (args != null) {
            Text(args, color = colors.muted, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
        }
        if (output != null) {
            CappedText(item.id, "raw_output", output, colors.muted, "pi_tool_output_toggle")
        }
    }
}

@Composable
private fun CappedText(itemId: String, slot: String, text: String, color: Color, toggleTag: String) {
    val colors = LlmTheme.colors
    var showAll by rememberSaveable(itemId, slot) { mutableStateOf(false) }
    var wrap by rememberSaveable(itemId, slot, "wrap") { mutableStateOf(true) }
    val lines = text.lines()
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Box(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(colors.surface).padding(8.dp),
        ) {
            Text(
                if (showAll) text else lines.take(MAX_LINES).joinToString("\n"),
                color = color,
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodySmall,
                softWrap = wrap,
                modifier = if (wrap) {
                    Modifier.fillMaxWidth().padding(end = 24.dp)
                } else {
                    Modifier.horizontalScroll(rememberScrollState()).padding(end = 24.dp)
                },
            )
            Icon(
                AppIcons.WrapText,
                contentDescription = if (wrap) "Turn off word wrap" else "Turn on word wrap",
                tint = if (wrap) colors.accent else colors.muted,
                modifier = Modifier.align(Alignment.TopEnd).size(20.dp).clickable { wrap = !wrap }.testTag("pi_tool_wrap_$slot"),
            )
        }
        if (lines.size > MAX_LINES) {
            Text(
                if (showAll) "Show less" else "Show all",
                color = colors.accent,
                style = MaterialTheme.typography.labelMedium,
                modifier = Modifier.clickable { showAll = !showAll }.testTag(toggleTag),
            )
        }
    }
}

private fun imageLabel(image: ToolImage): String {
    val bytes = image.byteSize()
    val size = if (bytes >= 1024) "${bytes / 1024} KB" else "$bytes B"
    return "${image.mimeType} · $size"
}
