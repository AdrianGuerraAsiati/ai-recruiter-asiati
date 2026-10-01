package com.asiati.talentid.core.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

data class DeviceCredentials(
    val deviceId: String,
    val secret: String,
)

class DeviceCredentialStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    fun save(credentials: DeviceCredentials) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())

        val encryptedSecret = cipher.doFinal(credentials.secret.toByteArray(Charsets.UTF_8))

        preferences.edit()
            .putString(KEY_DEVICE_ID, credentials.deviceId)
            .putString(KEY_SECRET_IV, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .putString(KEY_SECRET_CIPHERTEXT, Base64.encodeToString(encryptedSecret, Base64.NO_WRAP))
            .apply()
    }

    fun load(): DeviceCredentials? {
        val deviceId = preferences.getString(KEY_DEVICE_ID, null) ?: return null
        val iv = preferences.getString(KEY_SECRET_IV, null) ?: return null
        val ciphertext = preferences.getString(KEY_SECRET_CIPHERTEXT, null) ?: return null

        return runCatching {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(
                Cipher.DECRYPT_MODE,
                getOrCreateKey(),
                GCMParameterSpec(GCM_TAG_LENGTH_BITS, Base64.decode(iv, Base64.NO_WRAP)),
            )

            val decrypted = cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP))
            DeviceCredentials(
                deviceId = deviceId,
                secret = decrypted.toString(Charsets.UTF_8),
            )
        }.getOrElse {
            clear()
            null
        }
    }

    fun clear() {
        preferences.edit().clear().apply()
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(KEYSTORE_PROVIDER).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        val generator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES,
            KEYSTORE_PROVIDER,
        )
        val spec = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build()

        generator.init(spec)
        return generator.generateKey()
    }

    private companion object {
        const val PREFERENCES_NAME = "talent_id_device"
        const val KEY_DEVICE_ID = "device_id"
        const val KEY_SECRET_IV = "secret_iv"
        const val KEY_SECRET_CIPHERTEXT = "secret_ciphertext"

        const val KEYSTORE_PROVIDER = "AndroidKeyStore"
        const val KEY_ALIAS = "talent_id_device_secret"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val GCM_TAG_LENGTH_BITS = 128
    }
}
