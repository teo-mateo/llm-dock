package com.hpz.llmdockchat.feature.pi.transcript.tools

private val WHITESPACE = Regex("\\s+")

fun firstCollapsedLine(text: String): String =
    text.lineSequence().firstOrNull().orEmpty().replace(WHITESPACE, " ").trim()
