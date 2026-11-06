package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.data.dto.ProviderModelsResponseDto
import com.hpz.llmdockchat.data.model.ModelOption
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.testing.readFixture
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ProviderModelsMapperTest {

    private fun groups(json: String) = ApiJson.decodeFromString(ProviderModelsResponseDto.serializer(), json).toGroups()

    @Test
    fun `unconfigured, errored and empty providers contribute no group`() {
        val result = groups(readFixture("provider_models.json"))

        assertEquals(listOf("mistral"), result.map { it.id })
    }

    @Test
    fun `a usable provider keeps every model in server order, headed by its name, stale or not`() {
        val mistral = groups(readFixture("provider_models.json")).single()

        assertEquals("Mistral", mistral.name)
        assertEquals(
            listOf(
                ModelOption.ProviderModel("mistral", "Mistral", "mistral-large-latest", "mistral-large-latest"),
                ModelOption.ProviderModel("mistral", "Mistral", "codestral-latest", "Codestral"),
            ),
            mistral.models,
        )
        assertEquals(ModelRef.Provider("mistral", "codestral-latest"), mistral.models[1].ref)
    }

    @Test
    fun `missing fields fall back leniently`() {
        val result = groups("""{"providers":[{"id":"acme","configured":true,"models":[{"id":"m1"},{"label":"no id"}]}]}""")

        assertEquals("acme", result.single().name)
        assertEquals(listOf(ModelOption.ProviderModel("acme", "acme", "m1", "m1")), result.single().models)
    }

    @Test
    fun `an empty or absent providers list is no groups`() {
        assertTrue(groups("""{"providers":[]}""").isEmpty())
        assertTrue(groups("""{}""").isEmpty())
    }
}
