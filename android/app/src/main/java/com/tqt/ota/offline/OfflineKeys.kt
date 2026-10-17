package com.tqt.ota.offline

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import org.json.JSONObject

/** Stable per-installation key. Never exports or replaces an existing private key. Call on an IO dispatcher. */
class OfflineKeys {
    fun publicKeyHex(): String = OfflineCrypto.hex(OfflineCrypto.publicBytes(entry().certificate.publicKey))

    fun sessionManifest(grant: ByteArray, info: JSONObject): ByteArray {
        val key = entry()
        val public = OfflineCrypto.publicBytes(key.certificate.publicKey)
        return OfflineCrypto.sessionManifest(grant, info, public) { message ->
            val signer = Signature.getInstance("SHA256withECDSA")
            signer.initSign(key.privateKey)
            signer.update(message)
            OfflineCrypto.derToRaw(signer.sign())
        }
    }

    private fun entry(): KeyStore.PrivateKeyEntry = synchronized(KEY_LOCK) {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (!store.containsAlias(ALIAS)) {
            KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore").apply {
                initialize(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                    .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                    .setDigests(KeyProperties.DIGEST_SHA256)
                    .setUserAuthenticationRequired(false)
                    .build())
                generateKeyPair()
            }
        }
        val result = store.getEntry(ALIAS, null) as? KeyStore.PrivateKeyEntry
            ?: throw OfflineVerificationException("La clave offline del teléfono no está disponible. Los permisos previos requieren revisión.")
        OfflineCrypto.publicBytes(result.certificate.publicKey)
        result
    }

    companion object {
        private const val ALIAS = "com.tqt.ota.offline.p256.v1"
        private val KEY_LOCK = Any()
    }
}
