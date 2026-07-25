package com.hpz.llmdockchat.testing

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.rules.TestWatcher
import org.junit.runner.Description

/**
 * `viewModelScope` dispatches on Main, which does not exist on the JVM. The
 * dispatcher is unconfined so a launch runs up to its first real suspension
 * inside the call that started it — the state a test asserts on is then already
 * there, with no time to advance.
 */
@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class MainDispatcherRule : TestWatcher() {
    override fun starting(description: Description) = Dispatchers.setMain(UnconfinedTestDispatcher())
    override fun finished(description: Description) = Dispatchers.resetMain()
}
