package com.hpz.llmdockchat.core.prefs

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SerialWriteQueueTest {

    @Test
    fun `a confirmed write reports its own failure`() = runTest {
        val queue = SerialWriteQueue(backgroundScope)

        val result = queue.confirmed<Unit> { error("disk full") }

        assertTrue(result.isFailure)
        assertEquals("disk full", result.exceptionOrNull()?.message)
    }

    @Test
    fun `a write that is cancelled reports a failure instead of hanging`() = runTest {
        val queue = SerialWriteQueue(backgroundScope)

        val result = withTimeout(5_000) {
            queue.confirmed<Unit> { throw CancellationException("the queue went away") }
        }

        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull() is CancellationException)
    }

    @Test
    fun `drain waits for the writes posted before it`() = runTest {
        val queue = SerialWriteQueue(backgroundScope)
        val applied = mutableListOf<Int>()

        queue.post { applied += 1 }
        queue.post { applied += 2 }
        queue.drain()

        assertEquals(listOf(1, 2), applied)
    }
}
