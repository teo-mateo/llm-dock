package com.hpz.llmdockchat

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import com.hpz.llmdockchat.core.ui.theme.LLMDockChatTheme
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.foundation.FoundationScreen

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as LlmDockApplication).container
        setContent {
            LLMDockChatTheme {
                val serverUrl by container.serverUrlStore.baseUrl.collectAsState()
                Scaffold(
                    modifier = Modifier.fillMaxSize(),
                    containerColor = LlmTheme.colors.app,
                ) { innerPadding ->
                    FoundationScreen(
                        serverUrl = serverUrl,
                        modifier = Modifier.padding(innerPadding),
                    )
                }
            }
        }
    }
}
