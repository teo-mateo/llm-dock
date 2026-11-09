package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.tools.ToolKind
import com.hpz.llmdockchat.feature.pi.transcript.tools.classifyTool
import com.hpz.llmdockchat.feature.pi.transcript.tools.parseToolArgs
import com.hpz.llmdockchat.feature.pi.transcript.tools.parseToolResult

@Composable
fun PiToolBody(item: PiItem.Tool) {
    val colors = LlmTheme.colors
    var raw by rememberSaveable(item.id) { mutableStateOf(false) }
    val args = remember(item.args) { parseToolArgs(item.args) }
    val result = remember(item.output) { parseToolResult(item.output) }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (item.args != null || item.output != null) {
            ToolToggleLabel(if (raw) "Formatted" else "Raw", onClick = { raw = !raw }, tag = "pi_tool_raw_toggle")
        }
        if (raw) {
            RawToolBody(item)
        } else {
            when (classifyTool(item.name)) {
                ToolKind.BASH -> BashToolBody(item, args, result)
                ToolKind.EDIT -> EditToolBody(item, args, result)
                ToolKind.READ -> ReadToolBody(item, args, result)
                ToolKind.WRITE -> WriteToolBody(item, args, result)
                ToolKind.PROCESS -> ProcessToolBody(item, args, result)
                ToolKind.CHATTERBOX_SEND,
                ToolKind.CHATTERBOX_LOOK,
                ToolKind.CHATTERBOX_JOIN,
                ToolKind.CHATTERBOX_LEAVE,
                ToolKind.GENERIC,
                -> GenericFormattedBody(item, args, result)
            }
        }
        if (item.truncated) {
            Text("output truncated by pi-remote", color = colors.amber, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun RawToolBody(item: PiItem.Tool) {
    val colors = LlmTheme.colors
    val args = item.args
    val output = item.output
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (args != null) {
            Text(args, color = colors.muted, fontFamily = MonoFontFamily, style = MaterialTheme.typography.bodySmall)
        }
        if (output != null) {
            ToolTextCard(item.id, "raw_output", output, colors.muted, "pi_tool_output_toggle")
        }
    }
}
