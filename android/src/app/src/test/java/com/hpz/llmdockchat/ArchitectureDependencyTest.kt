package com.hpz.llmdockchat

import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The package layout is only as good as the next change's willingness to respect
 * it, so the directions this tree is supposed to have are checked against the
 * sources. One rule table rather than a test per pair: a hand-written pair list
 * is how the previous version missed `thread -> share`.
 *
 * References are matched anywhere in a file, not just on import lines, so a
 * fully-qualified use is caught the same as an import.
 */
class ArchitectureDependencyTest {

    private val sources: Map<String, String> = File("src/main/java").walkTopDown()
        .filter { it.extension == "kt" }
        .associate { it.path.replace('\\', '/') to it.readText() }

    private val featureReference = Regex("com\\.hpz\\.llmdockchat\\.feature\\.(\\w+)")

    private val featurePath = Regex("src/main/java/com/hpz/llmdockchat/feature/(\\w+)/")

    /** The composition root: the one file allowed to wire features together. */
    private val compositionRoot = "src/main/java/com/hpz/llmdockchat/core/AppContainer.kt"

    /**
     * Every cross-feature reference that exists today, with the reason it is
     * there. A feature may otherwise reference only `core`, `data` and itself,
     * so a new edge has to be added here deliberately.
     */
    private val crossFeature: Map<Pair<String, String>, String> = mapOf(
        ("conversations" to "account") to "account",
        ("modelpicker" to "newchat") to "sheet",
        ("modelpicker" to "thread") to "sheet",
        ("models" to "account") to "account",
        ("models" to "conversations") to "list",
        ("models" to "logs") to "logs",
        ("models" to "newchat") to "sheet",
        ("models" to "thread") to "control",
        ("newchat" to "conversations") to "list",
        ("newchat" to "modelpicker") to "picker",
        ("newchat" to "share") to "share",
        ("newchat" to "toolspicker") to "picker",
        ("share" to "conversations") to "row",
        ("share" to "modelpicker") to "model",
        ("thread" to "modelpicker") to "picker",
        ("toolspicker" to "newchat") to "sheet",
        ("toolspicker" to "thread") to "sheet",
    )

    private fun featureOf(path: String): String? =
        featurePath.find(path)?.groupValues?.get(1)

    private fun targets(body: String): Set<String> =
        featureReference.findAll(body).map { it.groupValues[1] }.toSet()

    @Test
    fun `a feature references only core, data and itself`() {
        assertTrue(sources.size > 50)
        val violations = sources.flatMap { (path, body) ->
            val feature = featureOf(path) ?: return@flatMap emptyList()
            targets(body)
                .filter { it != feature && crossFeature[feature to it] == null }
                .map { "$path -> feature.$it" }
        }
        assertTrue("undeclared cross-feature references: $violations", violations.isEmpty())
    }

    @Test
    fun `core references no feature except the composition root`() {
        val violations = sources
            .filterKeys { it.contains("/core/") && it != compositionRoot }
            .flatMap { (path, body) -> targets(body).map { "$path -> feature.$it" } }
        assertTrue("core must not depend on a feature: $violations", violations.isEmpty())
    }

    @Test
    fun `no exception has outlived its edge`() {
        val present = sources.flatMap { (path, body) ->
            val feature = featureOf(path) ?: return@flatMap emptyList()
            targets(body).map { feature to it }
        }.toSet()
        val stale = crossFeature.keys.filter { it !in present }
        assertTrue("exceptions with no reference left: $stale", stale.isEmpty())
    }
}
