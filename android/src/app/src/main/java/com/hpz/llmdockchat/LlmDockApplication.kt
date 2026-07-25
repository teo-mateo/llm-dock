package com.hpz.llmdockchat

import android.app.Application
import com.hpz.llmdockchat.core.AppContainer

class LlmDockApplication : Application() {

    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
