package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.argsSummary

fun toolSummary(item: PiItem.Tool): String = when (classifyTool(item.name)) {
    ToolKind.BASH, ToolKind.EDIT, ToolKind.READ, ToolKind.WRITE, ToolKind.PROCESS, ToolKind.CHATTERBOX, ToolKind.GENERIC ->
        argsSummary(item.args)
}
