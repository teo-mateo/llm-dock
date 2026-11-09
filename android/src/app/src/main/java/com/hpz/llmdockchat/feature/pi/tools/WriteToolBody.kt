package com.hpz.llmdockchat.feature.pi.tools

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.str
import com.hpz.llmdockchat.feature.pi.transcript.tools.ToolResult
import com.hpz.llmdockchat.feature.pi.transcript.tools.numberLines
import kotlinx.serialization.json.JsonObject

@Composable
internal fun WriteToolBody(item: PiItem.Tool, args: JsonObject?, result: ToolResult?) {
    val path = args?.str("path")
    val content = args?.str("content").orEmpty()
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        ToolResultMessage(item, result, ToolResultMode.ERRORS_ONLY)
        if (path != null) PathHeader(path)
        val lines = remember(content) { numberLines(content, 1) }
        if (lines.isNotEmpty()) NumberedText(item.id, "write_content", lines, 20)
        ToolResultMessage(item, result, ToolResultMode.SUCCESS_ONLY)
    }
}
