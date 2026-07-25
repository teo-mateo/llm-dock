package com.hpz.llmdockchat.core.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * [parseGpuStreamFrame] against the shapes `gpu_stream` actually sends
 * (`dashboard/routes/gpu.py:gpu_stream`) — a bare `{"gpus": […]}` tick, or
 * `{"error": …}` when that tick's `nvidia-smi` call itself failed. Unlike
 * `services_stream` there is no `type` envelope at all.
 */
class GpuStreamEventParserTest {

    @Test
    fun `a normal tick decodes every gpu's memory, utilisation, temperature and power`() {
        val event = parseGpuStreamFrame(
            """
            {"gpus": [{"index": 0, "name": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
              "memory": {"total": 97887, "used": 95312, "free": 1935, "unit": "MiB", "utilization_percent": 11},
              "temperature": {"current": 37, "unit": "C"},
              "utilization": {"gpu_percent": 5, "memory_percent": 11},
              "power": {"draw": 20.72, "limit": {"current": 300.0, "default": 600.0, "min": 150.0, "max": 600.0, "enforced": 300.0}, "unit": "W"}
            }], "timestamp": "2026-07-25T00:00:00Z"}
            """.trimIndent(),
        )
        val frame = event as GpuStreamEvent.Frame
        assertEquals(1, frame.gpus.size)
        val gpu = frame.gpus[0]
        assertEquals("NVIDIA RTX PRO 6000 Blackwell Workstation Edition", gpu.name)
        assertEquals(97887, gpu.memory.total)
        assertEquals(95312, gpu.memory.used)
        assertEquals(37, gpu.temperature.current)
        assertEquals(5, gpu.utilization.gpuPercent)
        assertEquals(20.72, gpu.power.draw, 0.001)
        assertEquals(300.0, gpu.power.limit.enforced, 0.001)
    }

    @Test
    fun `an error tick with no gpus key is Error, not Unknown`() {
        val event = parseGpuStreamFrame("""{"error": "GPU stats unavailable: nvidia-smi command failed"}""")
        assertEquals(GpuStreamEvent.Error("GPU stats unavailable: nvidia-smi command failed"), event)
    }

    @Test
    fun `no GPU present is an empty gpus list, a Frame not an Error`() {
        val event = parseGpuStreamFrame("""{"gpus": [], "timestamp": "2026-07-25T00:00:00Z"}""")
        assertEquals(GpuStreamEvent.Frame(emptyList()), event)
    }

    @Test
    fun `garbage that is not JSON at all never throws`() {
        assertEquals(GpuStreamEvent.Unknown("not json"), parseGpuStreamFrame("not json"))
    }

    @Test
    fun `a payload with neither gpus nor error is Unknown rather than a crash`() {
        val payload = """{"something_else": 1}"""
        assertTrue(parseGpuStreamFrame(payload) is GpuStreamEvent.Unknown)
    }
}
