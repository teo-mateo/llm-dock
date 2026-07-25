package com.hpz.llmdockchat.data.model

/** Level colouring is derived, best-effort — [PLAIN] is the safe default for anything unrecognised. */
enum class LogLevel { ERROR, WARN, INFO, PLAIN }

/**
 * F12-R4: colour by level where the line makes it derivable. This is pattern
 * matching over unstructured container output, not a log parser — it must
 * never throw, never touch the line's text, and degrade to [LogLevel.PLAIN]
 * for anything it doesn't recognise (F12-R4's second criterion). Checked in
 * priority order so a line mentioning both, e.g. "WARN: retrying after ERROR",
 * reads as the more severe of the two.
 */
fun classifyLogLevel(line: String): LogLevel = when {
    ERROR_PATTERN.containsMatchIn(line) -> LogLevel.ERROR
    WARN_PATTERN.containsMatchIn(line) -> LogLevel.WARN
    INFO_PATTERN.containsMatchIn(line) -> LogLevel.INFO
    else -> LogLevel.PLAIN
}

private val ERROR_PATTERN = Regex("\\b(ERROR|CRITICAL|FATAL|EXCEPTION|TRACEBACK)\\b", RegexOption.IGNORE_CASE)
private val WARN_PATTERN = Regex("\\bWARN(ING)?\\b", RegexOption.IGNORE_CASE)
private val INFO_PATTERN = Regex("\\bINFO\\b", RegexOption.IGNORE_CASE)
