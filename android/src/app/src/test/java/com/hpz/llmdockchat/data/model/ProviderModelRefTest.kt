package com.hpz.llmdockchat.data.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

class ProviderModelRefTest {

    @Test
    fun `provider, openrouter and local refs round-trip through parse and wireValue unchanged`() {
        listOf("mistral:mistral-large-latest", "acme:org/model:tag", "openrouter:vendor/m", "llamacpp-gemma")
            .forEach { assertEquals(it, parseModelRef(it).wireValue) }
    }

    @Test
    fun `a provider ref splits on the first colon only`() {
        assertEquals(ModelRef.Provider("acme", "org/model:tag"), parseModelRef("acme:org/model:tag"))
        assertEquals(ModelRef.Provider("mistral", "mistral-large-latest"), parseModelRef("mistral:mistral-large-latest"))
    }

    @Test
    fun `openrouter is never a provider id`() {
        assertEquals(ModelRef.OpenRouter("vendor/m"), parseModelRef("openrouter:vendor/m"))
        assertFalse(parseModelRef("openrouter:") is ModelRef.Provider)
    }

    @Test
    fun `an id outside the provider grammar or an empty model id is not a provider ref`() {
        assertEquals(ModelRef.Local("Bad:x"), parseModelRef("Bad:x"))
        assertEquals(ModelRef.Local("mistral:"), parseModelRef("mistral:"))
        assertEquals(ModelRef.Local("m:x"), parseModelRef("m:x"))
        assertEquals(ModelRef.Local("9ab:x"), parseModelRef("9ab:x"))
        assertEquals(ModelRef.Local(":x"), parseModelRef(":x"))
        assertEquals(ModelRef.Local("a".repeat(33) + ":x"), parseModelRef("a".repeat(33) + ":x"))
        assertEquals(ModelRef.Provider("a".repeat(32), "x"), parseModelRef("a".repeat(32) + ":x"))
        assertEquals(ModelRef.Provider("my-co2", "x"), parseModelRef("my-co2:x"))
    }

    @Test
    fun `a provider ref displays as its model id and is the provider engine`() {
        val ref = parseModelRef("mistral:mistral-large-latest")
        assertEquals("mistral-large-latest", ref.displayName)
        assertEquals(Engine.PROVIDER, ref.engine)
    }

    @Test
    fun `the chip names the provider, falling back to its id when the name is unknown`() {
        val ref = parseModelRef("mistral:mistral-large-latest")
        assertEquals("Mistral", ref.providerLabel(mapOf("mistral" to "Mistral")))
        assertEquals("mistral", ref.providerLabel())
        assertEquals("mistral", ref.providerLabel(mapOf("mistral" to " ")))
        assertEquals("mistral · mistral-large-latest", ref.chipLabel())
        assertEquals("Mistral · mistral-large-latest", ref.chipLabel(mapOf("mistral" to "Mistral")))
    }

    @Test
    fun `non-provider refs carry no provider label and keep their chip text`() {
        assertNull(parseModelRef("openrouter:vendor/m").providerLabel())
        assertNull(parseModelRef("llamacpp-gemma").providerLabel())
        assertEquals("vendor/m", parseModelRef("openrouter:vendor/m").chipLabel())
        assertEquals("llamacpp-gemma", parseModelRef("llamacpp-gemma").chipLabel())
    }
}
