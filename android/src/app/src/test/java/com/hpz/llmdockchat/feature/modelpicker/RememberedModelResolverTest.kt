package com.hpz.llmdockchat.feature.modelpicker

import com.hpz.llmdockchat.data.model.ModelOption
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The one remembered-model ladder, shared by the new-chat sheet and
 * the summarize path — the two must not disagree about when to ask.
 */
class RememberedModelResolverTest {

    private val running = ModelOption.LocalService("llamacpp-running", "running")
    private val stopped = ModelOption.LocalService("vllm-stopped", "exited")
    private val remote = ModelOption.Remote("anthropic/claude-sonnet-5", "Claude Sonnet 5")

    private fun resolve(raw: String?, preselected: String? = null, remoteModels: List<ModelOption.Remote> = listOf(remote)) =
        RememberedModelResolver.resolve(raw, listOf(running, stopped), remoteModels, preselected)

    @Test
    fun `a running remembered service is used as-is`() {
        assertEquals(RememberedModel.Resolved(running), resolve("llamacpp-running"))
    }

    @Test
    fun `a remembered service that stopped must be chosen again, not silently used`() {
        assertEquals(RememberedModel.Unavailable("vllm-stopped"), resolve("vllm-stopped"))
    }

    @Test
    fun `a remembered service that no longer exists is unavailable too`() {
        assertEquals(RememberedModel.Unavailable("llamacpp-renamed"), resolve("llamacpp-renamed"))
    }

    @Test
    fun `no prior chat is a plain absence, not an error`() {
        assertEquals(RememberedModel.None, resolve(null))
    }

    @Test
    fun `a remembered remote model uses its curated label`() {
        assertEquals(RememberedModel.Resolved(remote), resolve("openrouter:anthropic/claude-sonnet-5"))
    }

    /** The curated list is a picker, not an allowlist. */
    @Test
    fun `a remote model missing from the curated list is still valid`() {
        val resolved = resolve("openrouter:nova/proxy", remoteModels = emptyList()) as RememberedModel.Resolved
        assertEquals("nova/proxy", (resolved.option as ModelOption.Remote).modelId)
    }

    @Test
    fun `a preselected running service wins over what was remembered`() {
        val preselected = ModelOption.LocalService("llamacpp-preselected", "running")
        val resolved = RememberedModelResolver.resolve("llamacpp-running", listOf(running, preselected), emptyList(), "llamacpp-preselected")
        assertEquals(RememberedModel.Resolved(preselected), resolved)
    }

    /** A preselect that died between the tap and the load falls through. */
    @Test
    fun `a preselected service that stopped falls back to the remembered one`() {
        val stoppedPreselect = ModelOption.LocalService("llamacpp-preselected", "exited")
        val resolved = RememberedModelResolver.resolve(
            "llamacpp-running",
            listOf(running, stoppedPreselect),
            emptyList(),
            "llamacpp-preselected",
        )
        assertEquals(RememberedModel.Resolved(running), resolved)
    }

    @Test
    fun `a stopped preselect with an unavailable memory is unavailable`() {
        val resolved = RememberedModelResolver.resolve("vllm-stopped", listOf(running, stopped), emptyList(), "nothing")
        assertTrue(resolved is RememberedModel.Unavailable)
    }
}
