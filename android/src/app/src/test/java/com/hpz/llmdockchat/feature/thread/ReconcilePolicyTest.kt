package com.hpz.llmdockchat.feature.thread

import com.hpz.llmdockchat.core.error.AppError
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReconcilePolicyTest {

    @Test
    fun `a network failure is retried`() {
        assertTrue(AppError.Network(java.io.IOException("connection reset")).isTransientForReconcile())
    }

    @Test
    fun `a rate limit or a server failure is retried`() {
        listOf(429, 500, 501, 502, 503, 504).forEach { status ->
            assertTrue("$status must be retried", http(status).isTransientForReconcile())
        }
    }

    @Test
    fun `a client error is terminal`() {
        listOf(400, 401, 403, 404, 409, 422).forEach { status ->
            assertFalse("$status must end the turn", http(status).isTransientForReconcile())
        }
    }

    @Test
    fun `unreadable, unexpected and unauthenticated responses are terminal`() {
        assertFalse(AppError.Parse(IllegalStateException("bad json")).isTransientForReconcile())
        assertFalse(AppError.Unexpected(IllegalStateException("boom")).isTransientForReconcile())
        assertFalse(AppError.Unauthenticated.isTransientForReconcile())
    }

    private fun http(status: Int) = AppError.Http(status, "message", fromServer = false)
}
