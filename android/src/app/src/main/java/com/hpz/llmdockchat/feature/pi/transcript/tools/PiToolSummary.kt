package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.argsSummary

fun toolSummary(item: PiItem.Tool): String = when (item.name) {
    else -> argsSummary(item.args)
}
