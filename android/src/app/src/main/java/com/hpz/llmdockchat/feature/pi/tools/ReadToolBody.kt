package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import com.hpz.llmdockchat.feature.pi.transcript.int
import com.hpz.llmdockchat.feature.pi.transcript.str
import com.hpz.llmdockchat.feature.pi.transcript.tools.ToolResult
import com.hpz.llmdockchat.feature.pi.transcript.tools.numberLines
import kotlinx.serialization.json.JsonObject

@Composable
internal fun ReadToolBody(item: PiItem.Tool, args: JsonObject?, result: ToolResult?) {
    val colors = LlmTheme.colors
    val error = item.status == ToolStatus.ERROR || result?.isError == true
    val message = result?.text?.trim().orEmpty()
    val path = args?.str("path")
    val offset = args?.int("offset")
    val limit = args?.int("limit")
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (error && message.isNotEmpty()) {
            Text(message, color = colors.red, style = MaterialTheme.typography.labelSmall)
        }
        if (path != null) PathHeader(path)
        if (offset != null || limit != null) {
            Text(
                rangeText(offset, limit),
                color = colors.muted,
                fontFamily = MonoFontFamily,
                style = MaterialTheme.typography.labelSmall,
            )
        }
        val images = result?.images.orEmpty()
        if (images.isNotEmpty()) {
            images.forEach { ToolImageView(it) }
        } else {
            val lines = remember(result?.text, offset) { numberLines(result?.text.orEmpty(), offset ?: 1) }
            if (lines.isNotEmpty()) NumberedText(item.id, "read_content", lines, 20)
        }
    }
}

private fun rangeText(offset: Int?, limit: Int?): String = when {
    offset != null && limit != null -> "L$offset–${offset + limit - 1}"
    offset != null -> "L$offset–"
    else -> "first ${limit ?: 0} lines"
}
