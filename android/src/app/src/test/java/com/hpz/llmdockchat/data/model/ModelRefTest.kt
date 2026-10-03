package com.hpz.llmdockchat.data.model

import org.junit.Assert.assertEquals
import org.junit.Test

/** Engine derivation and the `openrouter:` display rule. */
class ModelRefTest {

    @Test
    fun `a vllm- prefix is the vllm engine`() {
        assertEquals(Engine.VLLM, parseModelRef("vllm-qwen3.6-35b-a3b-fp8").engine)
    }

    @Test
    fun `a llamacpp- prefix is the llama-cpp engine`() {
        assertEquals(Engine.LLAMA_CPP, parseModelRef("llamacpp-gemma-4-26b-a4b-it-q8").engine)
    }

    @Test
    fun `a ds4- prefix is the ds4 engine`() {
        assertEquals(Engine.DS4, parseModelRef("ds4-deepseek-v4-flash").engine)
    }

    @Test
    fun `a sglang- prefix is the sglang engine`() {
        assertEquals(Engine.SGLANG, parseModelRef("sglang-qwen3-8-flash-next-mixed-nvfp4-fp8").engine)
    }

    @Test
    fun `an ik- prefix is the ik_llama-cpp engine`() {
        assertEquals(Engine.IK_LLAMA_CPP, parseModelRef("ik-qwen3.6-27b-iq4xs").engine)
    }

    @Test
    fun `an exl3- prefix is the tabbyapi engine`() {
        assertEquals(Engine.TABBYAPI, parseModelRef("exl3-gemma-4-31b-it").engine)
    }

    @Test
    fun `a ninfer- prefix is the ninfer engine`() {
        assertEquals(Engine.NINFER, parseModelRef("ninfer-qwen3.8-27b-nvfp4").engine)
    }

    @Test
    fun `an openrouter model is the open-router engine regardless of its id`() {
        assertEquals(Engine.OPEN_ROUTER, parseModelRef("openrouter:anthropic/claude-sonnet-5").engine)
    }

    @Test
    fun `an unrecognised prefix falls back to unknown rather than crashing`() {
        assertEquals(Engine.UNKNOWN, parseModelRef("some-retired-service").engine)
    }

    @Test
    fun `an openrouter ref displays the model id, not the raw prefixed string`() {
        val ref = parseModelRef("openrouter:anthropic/claude-sonnet-5")
        assertEquals("anthropic/claude-sonnet-5", ref.displayName)
    }

    @Test
    fun `a local ref displays the service name`() {
        val ref = parseModelRef("llamacpp-laguna-s-2.1-q4")
        assertEquals("llamacpp-laguna-s-2.1-q4", ref.displayName)
    }
}
