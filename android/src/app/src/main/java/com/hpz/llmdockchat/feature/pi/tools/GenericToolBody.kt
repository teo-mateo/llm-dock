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
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import com.hpz.llmdockchat.feature.pi.transcript.tools.ToolImage
import com.hpz.llmdockchat.feature.pi.transcript.tools.ToolResult
import com.hpz.llmdockchat.feature.pi.transcript.tools.byteSize
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

@Composable
internal fun GenericFormattedBody(item: PiItem.Tool, args: JsonObject?, result: ToolResult?) {
    val colors = LlmTheme.colors
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        when {
            args != null && args.isNotEmpty() -> args.entries.forEach { (key, value) -> ArgRow(item.id, key, value) }
            item.args != null -> ToolTextCard(item.id, "args", item.args, colors.muted, "pi_tool_args_toggle")
        }
        if (result != null) {
            val error = result.isError || item.status == ToolStatus.ERROR
            if (result.text.isNotEmpty()) {
                ToolTextCard(item.id, "result", result.text, if (error) colors.red else colors.muted, "pi_tool_output_toggle")
            } else if (result.images.isEmpty() && item.output != null) {
                ToolTextCard(item.id, "result", item.output, if (error) colors.red else colors.muted, "pi_tool_output_toggle")
            }
            result.images.forEach { image ->
                Text(
                    imageLabel(image),
                    color = colors.muted,
                    fontFamily = MonoFontFamily,
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
        ToolTextCard(itemId, "arg_$key", text, colors.fg, "pi_tool_arg_${key}_toggle")
    }
}

private fun imageLabel(image: ToolImage): String {
    val bytes = image.byteSize()
    val size = if (bytes >= 1024) "${bytes / 1024} KB" else "$bytes B"
    return "${image.mimeType} · $size"
}
