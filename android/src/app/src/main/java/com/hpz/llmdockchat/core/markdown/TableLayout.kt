package com.hpz.llmdockchat.core.markdown

const val MAX_FITTED_TABLE_COLUMNS = 4

fun fittedColumnWeights(table: MdBlock.Table): List<Float>? {
    val columns = table.header.size
    if (columns == 0 || columns > MAX_FITTED_TABLE_COLUMNS) return null
    return List(columns) { index ->
        val longest = (listOf(table.header) + table.rows).maxOf { row -> row.getOrNull(index)?.length ?: 0 }
        longest.coerceIn(4, 40).toFloat()
    }
}
