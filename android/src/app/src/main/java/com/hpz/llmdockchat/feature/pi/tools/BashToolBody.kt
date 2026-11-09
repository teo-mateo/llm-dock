package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.int
import com.hpz.llmdockchat.feature.pi.transcript.str
import com.hpz.llmdockchat.feature.pi.transcript.tools.ToolResult
import com.hpz.llmdockchat.feature.pi.transcript.tools.bashExitCode
import com.hpz.llmdockchat.feature.pi.transcript.tools.bashOutput
import com.hpz.llmdockchat.feature.pi.transcript.tools.splitCdPrefix
import kotlinx.serialization.json.JsonObject

private const val OUTPUT_LINES = 12

@Composable
internal fun BashToolBody(item: PiItem.Tool, args: JsonObject?, result: ToolResult?) {
    val colors = LlmTheme.colors
    val command = args?.str("command") ?: item.args.orEmpty()
    val parsed = splitCdPrefix(command)
    val timeout = args?.int("timeout")
    val output = bashOutput(result)
    val exit = bashExitCode(result)
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        parsed.dir?.let { WorkingDirectoryChip(it) }
        ShellCommandCard(item.id, "bash_command", parsed.command)
        if (timeout != null) {
            Text("timeout $timeout s", color = colors.muted, style = MaterialTheme.typography.labelSmall)
        }
        when {
            output == null -> Unit
            output.isEmpty() -> Text("(no output)", color = colors.muted, style = MaterialTheme.typography.labelSmall)
            else -> ToolTextCard(
                itemId = item.id,
                slot = "bash_output",
                text = output,
                color = colors.muted,
                toggleTag = "pi_tool_output_toggle",
                maxLines = OUTPUT_LINES,
                toggleLabel = { n -> "Show all $n lines" },
                wrapByDefault = false,
            )
        }
        if (exit != null && exit != 0) {
            Text("exit $exit", color = colors.red, style = MaterialTheme.typography.labelMedium, fontFamily = MonoFontFamily)
        }
    }
}
