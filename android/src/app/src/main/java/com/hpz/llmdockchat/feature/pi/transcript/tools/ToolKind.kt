package com.hpz.llmdockchat.feature.pi.transcript.tools

enum class ToolKind {
    BASH,
    EDIT,
    READ,
    WRITE,
    PROCESS,
    CHATTERBOX_SEND,
    CHATTERBOX_LOOK,
    CHATTERBOX_JOIN,
    CHATTERBOX_LEAVE,
    GENERIC,
}

fun classifyTool(name: String): ToolKind = when (name) {
    "bash" -> ToolKind.BASH
    "edit" -> ToolKind.EDIT
    "read" -> ToolKind.READ
    "write" -> ToolKind.WRITE
    "process" -> ToolKind.PROCESS
    "chatterbox_send" -> ToolKind.CHATTERBOX_SEND
    "chatterbox_look" -> ToolKind.CHATTERBOX_LOOK
    "chatterbox_join" -> ToolKind.CHATTERBOX_JOIN
    "chatterbox_leave" -> ToolKind.CHATTERBOX_LEAVE
    else -> ToolKind.GENERIC
}
