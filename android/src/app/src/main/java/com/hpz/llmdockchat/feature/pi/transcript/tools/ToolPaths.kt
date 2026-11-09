package com.hpz.llmdockchat.feature.pi.transcript.tools

data class SplitPath(val dir: String, val name: String)

fun splitPath(path: String): SplitPath {
    val slash = path.lastIndexOf('/')
    if (slash < 0) return SplitPath("", path)
    return SplitPath(path.substring(0, slash + 1), path.substring(slash + 1))
}
