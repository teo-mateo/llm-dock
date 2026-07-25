package com.hpz.llmdockchat.core.auth

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Symmetric encryption for the one secret the app stores at rest.
 *
 * An interface, not a helper object, for two reasons: the Android Keystore
 * needs a device, and the store that uses it must stay unit-testable.
 * Both methods return null rather than throwing — an unreadable secret is
 * equivalent to no secret, and losing it costs one sign-in.
 */
interface SecretCipher {
    fun encrypt(plaintext: String): String?
    fun decrypt(ciphertext: String): String?
}

/**
 * AES-256/GCM with the key held in the platform Keystore, so the key material
 * never enters the app's process (Architecture U1 — `androidx.security:
 * security-crypto` is deprecated in full and must not be used).
 *
 * The output is `base64(iv || ciphertext||tag)`, which is what lands in
 * DataStore. Without the Keystore key that blob is inert, so a copy of the
 * preferences file taken off the device yields nothing.
 */
class KeystoreSecretCipher(
    private val alias: String = DEFAULT_ALIAS,
) : SecretCipher {

    override fun encrypt(plaintext: String): String? = runCatching {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val iv = cipher.iv
        val body = cipher.doFinal(plaintext.toByteArray(Charsets.UTF_8))
        Base64.encodeToString(iv + body, Base64.NO_WRAP)
    }.getOrNull()

    override fun decrypt(ciphertext: String): String? = runCatching {
        val raw = Base64.decode(ciphertext, Base64.NO_WRAP)
        if (raw.size <= IV_BYTES) return null
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(
            Cipher.DECRYPT_MODE,
            key(),
            GCMParameterSpec(TAG_BITS, raw, 0, IV_BYTES),
        )
        String(cipher.doFinal(raw, IV_BYTES, raw.size - IV_BYTES), Charsets.UTF_8)
    }.getOrNull()

    /**
     * Created on first use and reused after. Synchronised because a 401 storm
     * can reach this from several OkHttp threads at once, and two threads
     * generating the same alias would leave one holding a key that no longer
     * decrypts what the other wrote.
     */
    @Synchronized
    private fun key(): SecretKey {
        val keyStore = KeyStore.getInstance(PROVIDER).apply { load(null) }
        (keyStore.getEntry(alias, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, PROVIDER)
        generator.init(
            KeyGenParameterSpec.Builder(
                alias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(KEY_BITS)
                // Deliberately not `setUserAuthenticationRequired`: that is
                // F01-R8's biometric gate, which is out of scope for v1. Adding
                // it here would lock the credential behind a prompt the app has
                // no UI for.
                .build(),
        )
        return generator.generateKey()
    }

    companion object {
        const val DEFAULT_ALIAS = "llm_dock_credential_v1"
        private const val PROVIDER = "AndroidKeyStore"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val IV_BYTES = 12
        private const val TAG_BITS = 128
        private const val KEY_BITS = 256
    }
}
