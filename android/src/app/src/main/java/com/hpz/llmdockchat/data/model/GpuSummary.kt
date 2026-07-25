package com.hpz.llmdockchat.data.model

/** One GPU, as F10-R3's header shows it — real numbers only, no per-container split (F10-R4). */
data class GpuSummary(
    val index: Int,
    val name: String,
    val memoryUsedMiB: Int,
    val memoryTotalMiB: Int,
    val utilizationPercent: Int,
    val temperatureC: Int,
    val powerDrawW: Double,
    val powerLimitW: Double,
) {
    /**
     * [name] without the boilerplate every card in a range repeats — this host
     * reports "NVIDIA RTX PRO 6000 Blackwell Workstation Edition", of which
     * only "RTX PRO 6000 Blackwell" identifies anything. On a phone the full
     * string crowds out the VRAM figure, which is what the header is for.
     */
    val shortName: String
        get() = name
            .removePrefix("NVIDIA ")
            .removeSuffix(" Workstation Edition")
            .removeSuffix(" Laptop GPU")
            .trim()
}

/**
 * What the GPU header shows, live from `GET /api/gpu/stream`. [Unavailable]
 * covers both shapes the endpoint can hand back for "nothing to show": an
 * `{"error": …}` frame (`nvidia-smi` failed) and a `{"gpus": []}` frame (no
 * GPU present) — the service list must keep working in either case (F10-R3's
 * fourth criterion).
 */
sealed interface GpuState {
    data class Available(val gpus: List<GpuSummary>) : GpuState
    data class Unavailable(val message: String?) : GpuState
}
