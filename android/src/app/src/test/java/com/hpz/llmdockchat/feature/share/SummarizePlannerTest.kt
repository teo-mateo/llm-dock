package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.core.prefs.SummarizeDefaults
import com.hpz.llmdockchat.data.model.ServiceSummary
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * F16's row visibility and routing, decided without a server or an `Intent`:
 * what counts as a shareable URL, which shares get the row, and when the tap
 * creates outright versus handing off to the new-chat sheet.
 */
class SummarizePlannerTest {

    private val running = ServiceSummary(name = "vllm-qwen", status = "running", kind = "chat")
    private val stopped = ServiceSummary(name = "vllm-qwen", status = "exited", kind = "chat")
    private val embedder = ServiceSummary(name = "vllm-bge", status = "running", kind = "embedding")
    private val services = listOf(running, stopped, embedder)
    private val web = listOf("webfetch", "websearch")

    private fun textShare(text: String) = StagedShare(text = text, origin = StagedOrigin.TEXT)

    private fun plan(
        share: StagedShare?,
        stored: List<String>? = null,
        registry: List<String> = web,
        remembered: String? = "vllm-qwen",
        services: List<ServiceSummary> = this.services,
    ) = SummarizePlanner.plan(
        share = share,
        prompt = "SUMMARIZE",
        storedToolIds = stored,
        registry = registry,
        rememberedModel = remembered,
        services = services,
    )

    // -- which share gets the row ------------------------------------------

    @Test
    fun `a shared link gets the row and the url is what is sent`() {
        val plan = plan(textShare("https://example.com/page"))

        assertEquals(
            SummarizePlan.CreateOn("vllm-qwen", "SUMMARIZE\n\nhttps://example.com/page", web),
            plan,
        )
    }

    @Test
    fun `title text beside the link keeps the url and drops the rest`() {
        val share = textShare("Interesting read on llms https://example.com/a/b?x=1 — worth a look")

        assertEquals("https://example.com/a/b?x=1", SummarizePlanner.urlIn(share))
    }

    @Test
    fun `punctuation a sharing app glued to the link is not part of the url`() {
        assertEquals(
            "https://example.com/a",
            SummarizePlanner.urlIn(textShare("look at this: https://example.com/a.")),
        )
    }

    @Test
    fun `shared text with no link gets no row`() {
        assertNull(SummarizePlanner.urlIn(textShare("no link in this paragraph at all")))
        assertEquals(SummarizePlan.Hidden, plan(textShare("no link in this paragraph at all")))
    }

    @Test
    fun `an image share gets no row`() {
        val image = StagedShare(attachments = listOf("data:image/jpeg;base64,AAA"), origin = StagedOrigin.IMAGE)
        assertNull(SummarizePlanner.urlIn(image))
        assertEquals(SummarizePlan.Hidden, plan(image))
    }

    @Test
    fun `a text file quoting a url gets no row`() {
        val file = StagedShare(
            text = "**Attached file: `notes.md`**\n\n```markdown\nsee https://example.com\n```",
            origin = StagedOrigin.TEXT_FILE,
        )
        assertNull(SummarizePlanner.urlIn(file))
        assertEquals(SummarizePlan.Hidden, plan(file))
    }

    @Test
    fun `a rejected share gets no row`() {
        val rejected = StagedShare(error = "PDFs can't be shared into a chat", origin = StagedOrigin.UNSUPPORTED)
        assertEquals(SummarizePlan.Hidden, plan(rejected))
    }

    // -- tools -------------------------------------------------------------

    @Test
    fun `nothing stored preselects the defaults that the registry reports`() {
        val plan = plan(textShare("https://example.com"), registry = listOf("websearch", "sympy-math", "webfetch"))

        assertEquals(web, (plan as SummarizePlan.CreateOn).toolIds)
    }

    @Test
    fun `one default present is enough to offer the row`() {
        val plan = plan(textShare("https://example.com"), registry = listOf("websearch"))

        assertEquals(listOf("websearch"), (plan as SummarizePlan.CreateOn).toolIds)
    }

    @Test
    fun `no fetch or search tool in the registry hides the row`() {
        assertEquals(
            SummarizePlan.Hidden,
            plan(textShare("https://example.com"), registry = listOf("sympy-math", "render-html")),
        )
    }

    @Test
    fun `an empty stored selection hides the row even when the defaults are present`() {
        assertEquals(SummarizePlan.Hidden, plan(textShare("https://example.com"), stored = emptyList()))
    }

    @Test
    fun `a stored selection is honoured over the defaults and narrowed to the registry`() {
        val plan = plan(
            textShare("https://example.com"),
            stored = listOf("browser-fetch", "webfetch"),
            registry = listOf("websearch", "browser-fetch"),
        )

        assertEquals(listOf("browser-fetch"), (plan as SummarizePlan.CreateOn).toolIds)
    }

    // -- model routing -----------------------------------------------------

    @Test
    fun `no remembered model falls through to the new-chat sheet with the flow armed`() {
        val plan = plan(textShare("https://example.com"), remembered = null)

        assertEquals(SummarizePlan.PickModelFirst("SUMMARIZE\n\nhttps://example.com", web), plan)
    }

    @Test
    fun `a remembered model that is not running falls through rather than routing around F03-R1`() {
        val stoppedOnly = listOf(ServiceSummary("vllm-qwen", "exited", "chat"))

        assertEquals(
            SummarizePlan.PickModelFirst("SUMMARIZE\n\nhttps://example.com", web),
            plan(textShare("https://example.com"), remembered = "vllm-qwen", services = stoppedOnly),
        )
    }

    @Test
    fun `a remembered model that is not a chat service falls through`() {
        assertEquals(
            SummarizePlan.PickModelFirst("SUMMARIZE\n\nhttps://example.com", web),
            plan(textShare("https://example.com"), remembered = "vllm-bge"),
        )
    }

    @Test
    fun `a remembered model that no longer exists falls through`() {
        assertEquals(
            SummarizePlan.PickModelFirst("SUMMARIZE\n\nhttps://example.com", web),
            plan(textShare("https://example.com"), remembered = "vllm-deleted"),
        )
    }

    @Test
    fun `a remembered remote model is used outright`() {
        assertEquals(
            SummarizePlan.CreateOn("openrouter:anthropic/claude-sonnet-5", "SUMMARIZE\n\nhttps://example.com", web),
            plan(textShare("https://example.com"), remembered = "openrouter:anthropic/claude-sonnet-5"),
        )
    }

    @Test
    fun `the built-in prompt is what a fresh install composes with`() {
        val composed = SummarizePlanner.message(SummarizeDefaults.PROMPT, "https://example.com")

        assertEquals("${SummarizeDefaults.PROMPT}\n\nhttps://example.com", composed)
    }
}
