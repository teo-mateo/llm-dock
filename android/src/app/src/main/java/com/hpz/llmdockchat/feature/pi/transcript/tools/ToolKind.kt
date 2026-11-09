package com.hpz.llmdockchat.feature.pi.transcript.tools

enum class ToolKind {
    BASH,
    EDIT,
    READ,
    WRITE,
    PROCESS,
    CHATTERBOX,
    GENERIC,
}

fun classifyTool(name: String): ToolKind = when (name) {
    "bash" -> ToolKind.BASH
    "edit" -> ToolKind.EDIT
    "read" -> ToolKind.READ
    "write" -> ToolKind.WRITE
    "process" -> ToolKind.PROCESS
    "chatterbox_send", "chatterbox_look", "chatterbox_join", "chatterbox_leave" -> ToolKind.CHATTERBOX
    else -> ToolKind.GENERIC
}
