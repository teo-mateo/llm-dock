package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.argsSummary
import com.hpz.llmdockchat.feature.pi.transcript.int
import com.hpz.llmdockchat.feature.pi.transcript.obj
import com.hpz.llmdockchat.feature.pi.transcript.str
import kotlinx.serialization.json.JsonObject

data class ProcessInfo(
    val action: String?,
    val id: String?,
    val name: String?,
    val pid: Int?,
    val status: String?,
    val exitCode: Int?,
    val command: String?,
    val cwd: String?,
)

enum class ProcessStatusTone {
    RUNNING,
    SUCCESS,
    FAILURE,
    NEUTRAL,
}

fun processInfo(args: JsonObject?, result: ToolResult?): ProcessInfo {
    val details = result?.details
    val info = details?.obj("process") ?: details?.obj("result")?.obj("info")
    return ProcessInfo(
        action = details?.str("action") ?: args?.str("action"),
        id = info?.str("id") ?: details?.str("id") ?: args?.str("id"),
        name = info?.str("name") ?: details?.str("processName") ?: args?.str("name"),
        pid = info?.int("pid"),
        status = info?.str("status") ?: details?.str("processStatus"),
        exitCode = info?.int("exitCode") ?: details?.int("exitCode"),
        command = info?.str("command") ?: args?.str("command"),
        cwd = info?.str("cwd") ?: args?.str("cwd"),
    )
}

fun processStatusTone(status: String?, exitCode: Int?): ProcessStatusTone {
    if (exitCode != null && exitCode != 0) return ProcessStatusTone.FAILURE
    return when (status?.lowercase()) {
        "running" -> ProcessStatusTone.RUNNING
        "exited", "success" -> ProcessStatusTone.SUCCESS
        "failed", "killed" -> ProcessStatusTone.FAILURE
        else -> ProcessStatusTone.NEUTRAL
    }
}

fun processSummary(item: PiItem.Tool): String {
    val info = processInfo(parseToolArgs(item.args), parseToolResult(item.output))
    val label = info.name ?: info.id
    val base = when (info.action) {
        "start" -> buildString {
            append("start")
            if (!label.isNullOrEmpty()) append(" ").append(label)
            val command = info.command?.let(::firstCommandLine).orEmpty()
            if (command.isNotEmpty()) append(" · ").append(command)
        }
        "stop" -> if (label.isNullOrEmpty()) "stop" else "stop $label"
        "output" -> if (label.isNullOrEmpty()) "output" else "output $label"
        "list" -> "list"
        else -> return argsSummary(item.args)
    }
    return buildString {
        append(base)
        info.status?.takeIf { it.isNotEmpty() }?.let { append(" · ").append(it) }
        if (info.exitCode != null && info.exitCode != 0) append(" · exit ").append(info.exitCode)
    }
}

private val WHITESPACE = Regex("\\s+")

private fun firstCommandLine(command: String): String =
    splitCdPrefix(command).command.lineSequence().firstOrNull().orEmpty().replace(WHITESPACE, " ").trim()
