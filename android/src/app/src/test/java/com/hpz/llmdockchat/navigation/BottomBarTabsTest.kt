package com.hpz.llmdockchat.navigation

import org.junit.Assert.assertEquals
import org.junit.Test

class BottomBarTabsTest {

    @Test
    fun `the bottom bar carries exactly the shipped destinations`() {
        assertEquals(
            listOf(Destinations.CHATS to "Chats", Destinations.MODELS to "Models", Destinations.PI to "Pi"),
            BOTTOM_TABS.map { it.route to it.label },
        )
    }

    @Test
    fun `every tab is addressable by a tag of its own`() {
        val tags = BOTTOM_TABS.map { it.testTag }
        assertEquals(listOf("nav_tab_chats", "nav_tab_models", "nav_tab_pi"), tags)
        assertEquals(tags.size, tags.toSet().size)
    }

    @Test
    fun `no tab draws itself with the same glyph as another`() {
        assertEquals(BOTTOM_TABS.size, BOTTOM_TABS.map { it.icon.name }.toSet().size)
    }
}
