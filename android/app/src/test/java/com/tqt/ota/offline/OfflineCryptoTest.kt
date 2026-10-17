package com.tqt.ota.offline

import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Ephemeral JVM fixtures only. No production private key, device credential, or hardware. */
class OfflineCryptoTest {
    @Test fun signedGrantAndFreshBootReceiptVerify() {
        val f = Fixture()
        val grant = f.grant()
        val data = f.crypto.verifyGrant(grant)
        assertEquals("TQT-R2-V30-0067", data.name)
        assertEquals("3.0", data.hw)
        assertEquals("4.3.1", data.fw)
        assertEquals(9L, data.sourceCounter)
        assertEquals(65536L, data.imageBytes)
        assertArrayEquals(pub(f.device), data.devicePub)
        f.crypto.verifyBefore(grant, f.info())
        f.crypto.verifyAfter(grant, f.info(), f.info(after = true))
    }

    @Test fun productionAnchorRejectsAnEphemeralRoot() {
        val f = Fixture()
        assertThrows(OfflineVerificationException::class.java) { OfflineCrypto.verifyGrant(f.grant()) }
    }

    @Test fun grantTamperingAndAnotherRootAreRejected() {
        val f = Fixture()
        val grant = f.grant()
        for (at in listOf(0, 16, 32, 97, 162, 178, 182, 214, 246, 278, 282, 306, 314, 330, 336, 344, 407)) {
            val damaged = grant.copyOf().apply { this[at] = (this[at].toInt() xor 1).toByte() }
            assertThrows(OfflineVerificationException::class.java) { f.crypto.verifyGrant(damaged) }
        }
        assertThrows(OfflineVerificationException::class.java) { OfflineCrypto(pub(pair())).verifyGrant(grant) }
        assertThrows(OfflineVerificationException::class.java) { f.crypto.verifyGrant(grant.copyOf(407)) }
    }

    @Test fun invalidP256PointsAreRejectedEvenInsideSignedGrant() {
        val f = Fixture()
        for (start in listOf(32, 97)) {
            val body = f.grant().copyOfRange(0, 344)
            ByteArray(65).apply { this[0] = 4 }.copyInto(body, start)
            assertThrows(OfflineVerificationException::class.java) { f.crypto.verifyGrant(body + sign(f.root, body)) }
        }
    }

    @Test fun signedWrongHardwareNameVersionAndExhaustedCounterAreRejected() {
        val f = Fixture()
        for ((offset, size, value) in listOf(Triple(282, 24, "TQT-R1-V30-0067"), Triple(306, 8, "3.1"),
            Triple(314, 16, "4.2"), Triple(314, 16, "04.3"), Triple(314, 16, "4.03"), Triple(314, 16, "4.3.0.0.0"))) {
            val body = f.grant().copyOfRange(0, 344)
            value.toByteArray().copyOf(size).copyInto(body, offset)
            assertThrows(OfflineVerificationException::class.java) { f.crypto.verifyGrant(body + sign(f.root, body)) }
        }
        val body = f.grant().copyOfRange(0, 344)
        bytes32(0xffffffffL).copyInto(body, 178)
        assertThrows(OfflineVerificationException::class.java) { f.crypto.verifyGrant(body + sign(f.root, body)) }
    }

    @Test fun unterminatedOrNonCanonicalProfileIsRejected() {
        val f = Fixture()
        val body = f.grant().copyOfRange(0, 344)
        body[305] = 'X'.code.toByte() // Nonzero byte after the name's NUL.
        assertThrows(OfflineVerificationException::class.java) { f.crypto.verifyGrant(body + sign(f.root, body)) }
    }

    @Test fun sourceCounterDigestBootAndBoardMustMatchEvenWithValidDeviceSignature() {
        val f = Fixture()
        val grant = f.grant()
        val changes = listOf("offline_counter" to 10L, "app_sha256" to hex(ByteArray(32) { 77 }),
            "boot_valid" to false, "nombre" to "TQT-R2-V30-0068", "hw" to "3.1", "mac" to "11:22:33:44:55:67")
        for ((field, value) in changes) {
            val info = f.info().put(field, value)
            f.resign(info)
            assertThrows(OfflineVerificationException::class.java) { f.crypto.verifyBefore(grant, info) }
        }
    }

    @Test fun substitutedDevicePublicKeyAndMalformedInfoAreRejected() {
        val f = Fixture()
        val grant = f.grant()
        val wrong = f.info().put("offline_public_key", hex(pub(pair())))
        assertThrows(OfflineVerificationException::class.java) { f.crypto.verifyBefore(grant, wrong) }
        for (field in listOf("nonce", "offline_signature", "offline_anchor_id", "offline_last_grant")) {
            val info = f.info().put(field, "zz")
            assertThrows(OfflineVerificationException::class.java) { f.crypto.verifyBefore(grant, info) }
        }
        assertThrows(OfflineVerificationException::class.java) { f.crypto.verifyBefore(grant, f.info().put("offline_counter", 9.0)) }
    }

    @Test fun infoTamperingOrMixedSnapshotsNeverVerify() {
        val f = Fixture()
        for ((field, value) in listOf("nonce" to hex(ByteArray(16) { 55 }), "partition" to 0x150000,
            "boot_valid" to false, "offline_counter" to 10, "fw" to "4.3.2")) {
            val info = f.info().put(field, value)
            assertThrows(OfflineVerificationException::class.java) { f.crypto.verifySnapshot(info) }
        }
    }

    @Test fun phoneSessionSignsFreshNonceAndGrantHashAndRefusesAnotherPhone() {
        val f = Fixture()
        val grant = f.grant()
        val info = f.info()
        val manifest = f.crypto.sessionManifest(grant, info, pub(f.phone)) { sign(f.phone, it) }
        assertEquals(472, manifest.size)
        assertArrayEquals(grant, manifest.copyOfRange(0, 408))
        val transcript = "TQT-OFFLINE-SESSION-v1".toByteArray() + grant.copyOfRange(16, 32) +
            ByteArray(16) { 31 } + java.security.MessageDigest.getInstance("SHA-256").digest(grant)
        assertTrue(Signature.getInstance("SHA256withECDSA").run {
            initVerify(f.phone.public); update(transcript); verify(OfflineCrypto.rawToDer(manifest.copyOfRange(408, 472)))
        })
        val another = pair()
        assertThrows(OfflineVerificationException::class.java) { f.crypto.sessionManifest(grant, info, pub(another)) { sign(another, it) } }
        assertThrows(OfflineVerificationException::class.java) { f.crypto.sessionManifest(grant, info, pub(f.phone)) { sign(another, it) } }
    }

    @Test fun sessionSignatureChangesWhenFreshNonceChanges() {
        val f = Fixture()
        val grant = f.grant()
        val info = f.info().put("nonce", hex(ByteArray(16) { 99 }))
        f.resign(info)
        val manifest = f.crypto.sessionManifest(grant, info, pub(f.phone)) { sign(f.phone, it) }
        val previous = "TQT-OFFLINE-SESSION-v1".toByteArray() + grant.copyOfRange(16, 32) +
            ByteArray(16) { 31 } + java.security.MessageDigest.getInstance("SHA-256").digest(grant)
        assertFalse(Signature.getInstance("SHA256withECDSA").run {
            initVerify(f.phone.public); update(previous); verify(OfflineCrypto.rawToDer(manifest.copyOfRange(408, 472)))
        })
    }

    @Test fun receiptMustHaveExactGrantCounterDigestFirmwareAndConfirmedBoot() {
        val f = Fixture()
        val grant = f.grant()
        val changes = listOf("offline_last_grant" to hex(ByteArray(16) { 0 }), "offline_counter" to 9L,
            "offline_counter" to 11L, "app_sha256" to hex(f.source), "fw" to "4.3.2", "boot_valid" to false)
        for ((field, value) in changes) {
            val info = f.info(after = true).put(field, value)
            f.resign(info)
            assertThrows(OfflineVerificationException::class.java) { f.crypto.verifyAfter(grant, info) }
        }
    }

    @Test fun completeVerificationRequiresNewSessionAndNewPartition() {
        val f = Fixture()
        val grant = f.grant()
        val before = f.info()
        for ((field, value) in listOf("nonce" to before.get("nonce"), "partition" to before.get("partition"))) {
            val after = f.info(after = true).put(field, value)
            f.resign(after)
            assertThrows(OfflineVerificationException::class.java) { f.crypto.verifyAfter(grant, before, after) }
        }
    }

    @Test fun derAndRawRoundTripThroughJavaProvider() {
        val key = pair()
        repeat(32) {
            val der = Signature.getInstance("SHA256withECDSA").run { initSign(key.private); update(byteArrayOf(it.toByte())); sign() }
            assertArrayEquals(der, OfflineCrypto.rawToDer(OfflineCrypto.derToRaw(der)))
        }
    }

    @Test fun nonCanonicalOrInvalidDerAndRawScalarsAreRejected() {
        val invalid = listOf(byteArrayOf(), byteArrayOf(0x30, 6, 2, 1, 0, 2, 1, 1),
            byteArrayOf(0x30, 7, 2, 2, 0, 1, 2, 1, 1), byteArrayOf(0x30, 6, 2, 1, -1, 2, 1, 1),
            byteArrayOf(0x30, 6, 2, 1, 1, 2, 1, 1, 0))
        invalid.forEach { assertThrows(OfflineVerificationException::class.java) { OfflineCrypto.derToRaw(it) } }
        assertThrows(OfflineVerificationException::class.java) { OfflineCrypto.rawToDer(ByteArray(64)) }
        assertThrows(OfflineVerificationException::class.java) { OfflineCrypto.rawToDer(ByteArray(63)) }
        val scalarN = OfflineCrypto.decodeHex("ffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551", 32)
        assertThrows(OfflineVerificationException::class.java) { OfflineCrypto.rawToDer(scalarN + ByteArray(32) { 1 }) }
    }

    private class Fixture {
        val root = pair()
        val device = pair()
        val phone = pair()
        val crypto = OfflineCrypto(pub(root))
        val uuid = ByteArray(16) { (it + 1).toByte() }
        val source = ByteArray(32) { 11 }
        val target = ByteArray(32) { 22 }
        val rootId = java.security.MessageDigest.getInstance("SHA-256").digest(pub(root)).copyOf(8)

        fun grant(): ByteArray {
            val body = ByteArray(344)
            "TQT-OFFLINE-v1".toByteArray().copyOf(16).copyInto(body)
            uuid.copyInto(body, 16)
            pub(device).copyInto(body, 32)
            pub(phone).copyInto(body, 97)
            ByteArray(16) { 7 }.copyInto(body, 162)
            bytes32(9).copyInto(body, 178)
            source.copyInto(body, 182)
            ByteArray(32) { 33 }.copyInto(body, 214)
            target.copyInto(body, 246)
            bytes32(65536).copyInto(body, 278)
            "TQT-R2-V30-0067".toByteArray().copyOf(24).copyInto(body, 282)
            "3.0".toByteArray().copyOf(8).copyInto(body, 306)
            "4.3.1".toByteArray().copyOf(16).copyInto(body, 314)
            byteArrayOf(0x11, 0x22, 0x33, 0x44, 0x55, 0x66).copyInto(body, 330)
            rootId.copyInto(body, 336)
            return body + sign(root, body)
        }

        fun info(after: Boolean = false): JSONObject = JSONObject().put("nombre", "TQT-R2-V30-0067")
            .put("hw", "3.0").put("fw", if (after) "4.3.1" else "4.3")
            .put("mac", "11:22:33:44:55:66").put("ota_protocol", 1).put("offline_protocol", 1)
            .put("offline_public_key", hex(pub(device))).put("offline_counter", if (after) 10L else 9L)
            .put("offline_anchor_id", hex(rootId)).put("offline_last_grant", hex(if (after) uuid else ByteArray(16)))
            .put("nonce", hex(ByteArray(16) { if (after) 32 else 31 }))
            .put("app_sha256", hex(if (after) target else source)).put("boot_valid", true)
            .put("partition", if (after) 0x150000 else 0x10000).also { resign(it) }

        fun resign(info: JSONObject) {
            fun binary(field: String, size: Int) = OfflineCrypto.decodeHex(info.getString(field), size)
            val transcript = "TQT-OFFLINE-INFO-v1".toByteArray() + binary("nonce", 16) + binary("app_sha256", 32) +
                bytes32(info.getLong("offline_counter")) + bytes32(info.getLong("partition")) +
                byteArrayOf(if (info.getBoolean("boot_valid")) 1 else 0) +
                info.getString("nombre").toByteArray().copyOf(24) + info.getString("hw").toByteArray().copyOf(8) +
                info.getString("fw").toByteArray().copyOf(16) + OfflineCrypto.decodeHex(info.getString("mac").replace(":", ""), 6) +
                binary("offline_last_grant", 16)
            info.put("offline_signature", hex(sign(device, transcript)))
        }
    }

    companion object {
        private fun pair(): KeyPair = KeyPairGenerator.getInstance("EC").apply { initialize(ECGenParameterSpec("secp256r1")) }.generateKeyPair()
        private fun pub(pair: KeyPair): ByteArray = OfflineCrypto.publicBytes(pair.public)
        private fun hex(bytes: ByteArray): String = OfflineCrypto.hex(bytes)
        private fun bytes32(value: Long) = ByteArray(4) { (value ushr (it * 8)).toByte() }
        private fun sign(pair: KeyPair, bytes: ByteArray): ByteArray = OfflineCrypto.derToRaw(Signature.getInstance("SHA256withECDSA").run {
            initSign(pair.private); update(bytes); sign()
        })
    }
}
