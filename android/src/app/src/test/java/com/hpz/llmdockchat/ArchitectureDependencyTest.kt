package com.hpz.llmdockchat

import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The package layout is only as good as the next change's willingness to respect
 * it. These are the directions this tree is supposed to have, checked against the
 * sources rather than trusted: shared code must not reach back into a feature,
 * and the two features that used to depend on each other must not start again.
 */
class ArchitectureDependencyTest {

    private val sources: Map<String, String> = File("src/main/java").walkTopDown()
        .filter { it.extension == "kt" }
        .associate { it.path.replace('\\', '/') to it.readText() }

    private fun filesImporting(from: String, to: String): List<String> =
        sources.filter { (path, body) ->
            path.contains(from) && body.contains("import com.hpz.llmdockchat.$to")
        }.keys.toList()

    @Test
    fun `shared attachment and render code does not import a feature`() {
        assertTrue(sources.size > 50)
        assertTrue(
            "core/attachment must not depend on a feature: ${filesImporting("core/attachment/", "feature.")}",
            filesImporting("core/attachment/", "feature.").isEmpty(),
        )
        assertTrue(
            "core/ui/render must not depend on a feature: ${filesImporting("core/ui/render/", "feature.")}",
            filesImporting("core/ui/render/", "feature.").isEmpty(),
        )
    }

    @Test
    fun `share does not import the thread feature`() {
        assertTrue(
            "feature/share must not depend on feature/thread: ${filesImporting("feature/share/", "feature.thread")}",
            filesImporting("feature/share/", "feature.thread").isEmpty(),
        )
    }

    @Test
    fun `pi does not import thread rendering primitives`() {
        assertTrue(
            "feature/pi must not depend on feature/thread: ${filesImporting("feature/pi/", "feature.thread")}",
            filesImporting("feature/pi/", "feature.thread").isEmpty(),
        )
    }
}
