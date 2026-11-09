package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import com.hpz.llmdockchat.feature.pi.transcript.int
import com.hpz.llmdockchat.feature.pi.transcript.str

data class BashCommand(val dir: String?, val command: String)

private val CD_PREFIX = Regex("""^cd[ \t]+(?:"([^"]*)"|'([^']*)'|([^\s;&]+))[ \t]*(?:&&|;)[ \t]*""")

fun splitCdPrefix(command: String): BashCommand {
    val match = CD_PREFIX.find(command) ?: return BashCommand(null, command)
    val dir = match.groups[1]?.value ?: match.groups[2]?.value ?: match.groups[3]?.value
    return BashCommand(dir, command.substring(match.range.last + 1).trim())
}

fun bashOutput(result: ToolResult?): String? = result?.structured?.str("output") ?: result?.text

fun bashExitCode(result: ToolResult?): Int? = result?.structured?.int("exit_code")

fun bashSummary(item: PiItem.Tool): String {
    val command = parseToolArgs(item.args)?.str("command") ?: item.args.orEmpty()
    val result = parseToolResult(item.output)
    val first = firstCollapsedLine(splitCdPrefix(command).command)
    val exit = bashExitCode(result)
    val timedOut = item.status == ToolStatus.ERROR && result?.text?.contains("timed out") == true
    return buildString {
        append("$ ").append(first)
        if (exit != null && exit != 0) append(" · exit ").append(exit)
        if (timedOut) append(" · timed out")
    }
}
