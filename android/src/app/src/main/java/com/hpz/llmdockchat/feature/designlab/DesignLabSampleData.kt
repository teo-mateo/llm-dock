package com.hpz.llmdockchat.feature.designlab

/** Dummy data for the design-lab mockups. No network, no repositories. */

data class MockConversation(
    val title: String,
    val preview: String,
    val model: String,
    val engine: String,
    val time: String,
    val pinned: Boolean = false,
)

val MOCK_CONVERSATIONS = listOf(
    MockConversation("Refactor the run manager", "Cancellation should be cooperative, polled between…", "mimo-v2-5-q4", "llama.cpp", "2m", pinned = true),
    MockConversation("Compare FP8 vs bf16 latency", "At 0.55 utilization the FP8 checkpoint holds steady…", "qwen3.6-27b", "vLLM", "41m"),
    MockConversation("Schemdraw circuit sketch", "Here's a two-stage RC low-pass with the corner freq…", "gpt-oss-120b", "vLLM", "1h"),
    MockConversation("Android nav graph review", "TabScaffold pops up to CHATS with saveState=true…", "mimo-v2-5-q4", "llama.cpp", "3h"),
    MockConversation("Draft the release notes", "Session tokens now slide 8h on every request instead…", "claude-sonnet-5", "OpenRouter", "yesterday"),
    MockConversation("Benchmark ds4 spec decoding", "ngram-map-k4v with defaults gives +43-87% on code…", "ds4-laguna", "DS4", "2d"),
    MockConversation("Explain the FK triggers", "Root-only membership: spin-offs can't carry a project_id…", "mimo-v2-5-q4", "llama.cpp", "3d"),
)

sealed interface MockMessage {
    val fromUser: Boolean

    data class Text(val body: String, override val fromUser: Boolean) : MockMessage
    data class Code(val language: String, val body: String, override val fromUser: Boolean = false) : MockMessage
    data object Streaming : MockMessage {
        override val fromUser get() = false
    }
}

val MOCK_THREAD_TITLE = "Refactor the run manager"

val MOCK_MESSAGES = listOf(
    MockMessage.Text("Cancellation looks cooperative today, but is it actually polled anywhere or does it just set a flag nobody reads?", fromUser = true),
    MockMessage.Text(
        "It's polled between stream events in `ChatRunner`. Each loop iteration checks `expected_run_id` before forwarding a delta, so a stale Stop can't kill a newer run that started after it.",
        fromUser = false,
    ),
    MockMessage.Code(
        "python",
        "while not done:\n    if run.cancelled and run.id == expected_run_id:\n        return persistence.cancel()\n    delta = next(stream)\n    emit(delta)",
    ),
    MockMessage.Text("Right — and a cancelled run saves no assistant message at all?", fromUser = true),
    MockMessage.Streaming,
)

data class MockService(
    val name: String,
    val engine: String,
    val running: Boolean,
    val port: Int,
    val vram: String,
    val ctx: String,
)

val MOCK_GPU_USED_GB = 61.4
val MOCK_GPU_TOTAL_GB = 96.0
val MOCK_GPU_UTIL = 0.72

val MOCK_SERVICES = listOf(
    MockService("llamacpp-mimo-v2-5-q4", "llama.cpp", running = true, port = 3307, vram = "18 GB", ctx = "128K"),
    MockService("vllm-qwen3.6-27b-mtp", "vLLM", running = true, port = 3312, vram = "31 GB", ctx = "160K"),
    MockService("vllm-nomic-embed-text-v1.5", "vLLM", running = true, port = 3320, vram = "2 GB", ctx = "8K"),
    MockService("ds4-laguna-70b", "DS4", running = false, port = 3330, vram = "—", ctx = "64K"),
    MockService("vllm-gpt-oss-120b", "vLLM", running = false, port = 3340, vram = "—", ctx = "32K"),
)

data class MockDetail(
    val name: String,
    val engine: String,
    val running: Boolean,
    val port: Int,
    val alias: String,
    val vram: String,
    val ctx: String,
    val flags: List<String>,
)

val MOCK_MODEL_DETAIL = MockDetail(
    name = "vllm-qwen3.6-27b-mtp",
    engine = "vLLM",
    running = true,
    port = 3312,
    alias = "qwen3.6-27b-mtp",
    vram = "31.2 GB / 96 GB",
    ctx = "160,000 tokens",
    flags = listOf(
        "--gpu-memory-utilization 0.55",
        "--max-model-len 160000",
        "--dtype auto",
        "--tensor-parallel-size 1",
        "--enable-prefix-caching",
    ),
)
