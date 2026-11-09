package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import com.hpz.llmdockchat.feature.pi.transcript.str
import com.hpz.llmdockchat.feature.pi.transcript.tools.DiffKind
import com.hpz.llmdockchat.feature.pi.transcript.tools.DiffLine
import com.hpz.llmdockchat.feature.pi.transcript.tools.ToolResult
import com.hpz.llmdockchat.feature.pi.transcript.tools.fallbackDiff
import com.hpz.llmdockchat.feature.pi.transcript.tools.parsePatch
import com.hpz.llmdockchat.feature.pi.transcript.tools.splitPath
import kotlinx.serialization.json.JsonObject

private const val DIFF_LINES = 40

@Composable
internal fun EditToolBody(item: PiItem.Tool, args: JsonObject?, result: ToolResult?) {
    val colors = LlmTheme.colors
    var showAll by rememberSaveable(item.id, "edit_diff") { mutableStateOf(false) }
    val patch = result?.details?.str("patch")?.takeIf { it.isNotEmpty() }
    val diff = remember(patch, args) { if (patch != null) parsePatch(patch) else fallbackDiff(args) }
    val body = diff.filter { it.kind != DiffKind.HEADER }
    val error = item.status == ToolStatus.ERROR || result?.isError == true
    val message = result?.text?.trim().orEmpty()
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (message.isNotEmpty()) {
            Text(
                message,
                color = if (error) colors.red else colors.muted,
                style = MaterialTheme.typography.labelSmall,
            )
        }
        val path = args?.str("path")
        if (path != null) {
            val split = splitPath(path)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                if (split.dir.isNotEmpty()) {
                    Text(
                        split.dir,
                        color = colors.muted,
                        fontFamily = MonoFontFamily,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                }
                Text(
                    split.name,
                    color = colors.fg,
                    fontFamily = MonoFontFamily,
                    fontWeight = FontWeight.SemiBold,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                )
            }
        }
        if (body.isNotEmpty()) {
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(colors.surface).padding(8.dp),
            ) {
                body.take(if (showAll) body.size else DIFF_LINES).forEach { DiffRow(it) }
            }
            if (body.size > DIFF_LINES) {
                ToolToggleLabel(
                    if (showAll) "Show less" else "Show all ${body.size} lines",
                    onClick = { showAll = !showAll },
                    tag = "pi_tool_output_toggle",
                )
            }
        }
    }
}

@Composable
private fun DiffRow(line: DiffLine) {
    val colors = LlmTheme.colors
    val prefix: String
    val color: Color
    val background: Color
    when (line.kind) {
        DiffKind.ADD -> {
            prefix = "+"
            color = colors.fg
            background = colors.green.copy(alpha = 0.15f)
        }
        DiffKind.REMOVE -> {
            prefix = "-"
            color = colors.fg
            background = colors.red.copy(alpha = 0.15f)
        }
        DiffKind.HUNK -> {
            prefix = ""
            color = colors.muted
            background = Color.Transparent
        }
        else -> {
            prefix = " "
            color = colors.fg
            background = Color.Transparent
        }
    }
    Text(
        prefix + line.text,
        color = color,
        fontFamily = MonoFontFamily,
        style = MaterialTheme.typography.bodySmall,
        modifier = Modifier.fillMaxWidth().background(background).padding(vertical = 1.dp),
    )
}
