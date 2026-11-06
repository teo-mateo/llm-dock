package com.hpz.llmdockchat.core.markdown

import androidx.compose.ui.text.AnnotatedString
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TableLayoutTest {
    private fun table(header: List<String>, vararg rows: List<String>) = MdBlock.Table(
        header.map { AnnotatedString(it) },
        header.map { TableAlign.LEFT },
        rows.map { row -> row.map { AnnotatedString(it) } },
    )

    @Test
    fun `narrow tables get weights from their longest cell`() {
        val weights = fittedColumnWeights(table(listOf("Folder", "Count"), listOf("Personal/Andreea", "12")))
        assertEquals(listOf(16f, 5f), weights)
    }

    @Test
    fun `weights are clamped`() {
        assertEquals(listOf(4f, 40f), fittedColumnWeights(table(listOf("a", "x".repeat(90)))))
    }

    @Test
    fun `wide tables keep scrolling`() {
        assertNull(fittedColumnWeights(table(listOf("a", "b", "c", "d", "e"))))
    }
}
