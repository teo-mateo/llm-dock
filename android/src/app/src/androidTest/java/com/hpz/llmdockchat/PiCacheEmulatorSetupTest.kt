package com.hpz.llmdockchat

import android.os.Build
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.hpz.llmdockchat.core.auth.DataStoreCredentialStore
import com.hpz.llmdockchat.core.auth.DataStoreTokenStore
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.DataStoreServerUrlStore
import java.io.File
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PiCacheEmulatorSetupTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val container get() = (context.applicationContext as LlmDockApplication).container
    private val record get() = File(context.filesDir, "pi422-original-configuration.json")

    private fun requireBackup() {
        check(Build.HARDWARE in setOf("ranchu", "goldfish")) { "Reserved emulator required" }
        check(InstrumentationRegistry.getArguments().getString("pi422BackupConfirmed") == "true") {
            "Preserve and validate private app data and original APK before this fixture-only helper"
        }
    }

    private fun configuration(): JSONObject {
        val server = container.serverUrlStore.current()
        return JSONObject().put("server", server?.value ?: JSONObject.NULL)
            .put("token_present", container.tokenStore.current() != null)
            .put("credential_present", container.credentialStore.current() != null)
    }

    @Test
    fun recordOriginalWithoutLaunchingActivity() {
        requireBackup()
        check(!record.exists()) { "Original configuration record already exists" }
        record.writeText(configuration().toString())
    }

    @Test
    fun prepareFixtureWithoutLaunchingOriginalServer() = runBlocking {
        requireBackup()
        check(record.isFile) { "Record and privately preserve original configuration first" }
        val request = Request.Builder().url("http://127.0.0.1:3999/__fixture/transcript").build()
        OkHttpClient().newCall(request).execute().use {
            check(it.isSuccessful && JSONObject(it.body.string()).getString("session_id") == "fixture-cache") {
                "Expected loopback transcript fixture is not ready"
            }
        }
        container.sessionManager.signOut()
        container.serverUrlStore.set(checkNotNull(BaseUrl.restore("http://127.0.0.1:3999")))
        (container.tokenStore as DataStoreTokenStore).awaitPendingWrites()
        (container.credentialStore as DataStoreCredentialStore).awaitPendingWrites()
        (container.serverUrlStore as DataStoreServerUrlStore).awaitPendingWrites()
    }

    @Test
    fun verifyRestoredConfigurationWithoutLaunchingActivity() {
        requireBackup()
        val expected = JSONObject(record.readText())
        val actual = configuration()
        check(expected.optString("server") == actual.optString("server")) { "Original server was not restored" }
        check(expected.getBoolean("token_present") == actual.getBoolean("token_present")) {
            "Original token/Keystore state was not restored"
        }
        check(expected.getBoolean("credential_present") == actual.getBoolean("credential_present")) {
            "Original credential/Keystore state was not restored"
        }
    }
}
