package com.tqt.ota.offline

import java.math.BigInteger
import java.security.AlgorithmParameters
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.PublicKey
import java.security.Signature
import java.security.interfaces.ECPublicKey
import java.security.spec.ECGenParameterSpec
import java.security.spec.ECParameterSpec
import java.security.spec.ECPoint
import java.security.spec.ECPublicKeySpec
import org.json.JSONObject

data class GrantData(
    val uuid: String, val devicePub: ByteArray, val phonePub: ByteArray,
    val sourceCounter: Long, val sourceDigest: String, val targetDigest: String,
    val transferHash: String, val imageBytes: Long, val name: String, val hw: String,
    val fw: String, val mac: String, val rootId: String, val iv: ByteArray
)

class OfflineVerificationException(message: String) : IllegalArgumentException(message)

/** Implements protocols/offline-v1.json with public keys only; no unit or server private key. */
class OfflineCrypto internal constructor(anchor: ByteArray) {
    private val anchorBytes = anchor.copyOf()
    private val anchorPublic = publicKey(anchorBytes)
    private val anchorId = sha256(anchorBytes).copyOf(8)

    fun verifyGrant(grant: ByteArray): GrantData {
        check(grant.size == GRANT_BYTES, "El permiso offline debe tener 408 bytes.")
        check(grant.copyOfRange(0, 16).contentEquals(MAGIC), "Formato de permiso offline desconocido.")
        check(equal(grant.copyOfRange(336, 344), anchorId), "El permiso offline no corresponde al firmante autorizado.")
        check(verify(anchorPublic, grant.copyOfRange(0, 344), grant.copyOfRange(344, 408)), "La firma del permiso offline es inválida.")
        val device = grant.copyOfRange(32, 97)
        val phone = grant.copyOfRange(97, 162)
        publicKey(device)
        publicKey(phone)
        val name = asciiField(grant, 282, 24)
        val hw = asciiField(grant, 306, 8)
        val fw = asciiField(grant, 314, 16)
        check(name.matches(Regex("TQT[-_]R2[-_]V30[-_][0-9]{4}")) && hw == "3.0", "El permiso no pertenece a una TQT R2 HW 3.0.")
        check(compatibleVersion(fw), "El permiso requiere firmware 4.3 o posterior con versión canónica.")
        val counter = u32(grant, 178)
        check(counter < UINT32_MAX, "El contador offline está agotado.")
        val imageBytes = u32(grant, 278)
        check(imageBytes in 65536..0x140000L, "Longitud de imagen offline incompatible con la partición R2.")
        return GrantData(hex(grant.copyOfRange(16, 32)), device, phone, counter,
            hex(grant.copyOfRange(182, 214)), hex(grant.copyOfRange(246, 278)),
            hex(grant.copyOfRange(214, 246)), imageBytes, name, hw, fw,
            grant.copyOfRange(330, 336).joinToString(":") { "%02x".format(it.toInt() and 255) },
            hex(anchorId), grant.copyOfRange(162, 178))
    }

    fun verifyBefore(grant: ByteArray, info: JSONObject) {
        val data = verifyGrant(grant)
        val proof = verifiedInfo(data, info)
        check(proof.counter == data.sourceCounter, "El permiso offline ya fue consumido o pertenece a otro estado de la R2.")
        check(proof.digest == data.sourceDigest, "El firmware origen de la R2 no coincide con el permiso offline.")
        check(proof.bootValid, "La R2 aún no confirmó su arranque anterior.")
    }

    /** The two-argument form checks the signed receipt; use the three-argument form when pre-INFO exists. */
    fun verifyAfter(grant: ByteArray, info: JSONObject) {
        val data = verifyGrant(grant)
        val proof = verifiedInfo(data, info)
        check(proof.counter == data.sourceCounter + 1, "El contador de la R2 no confirma el consumo de este permiso.")
        check(proof.lastGrant == data.uuid, "El recibo de la R2 no corresponde a esta operación offline.")
        check(proof.digest == data.targetDigest && proof.fw == data.fw, "La R2 no está ejecutando la imagen autorizada.")
        check(proof.bootValid, "La R2 todavía no confirmó el nuevo arranque.")
    }

    fun verifyAfter(grant: ByteArray, before: JSONObject, after: JSONObject) {
        verifyBefore(grant, before)
        verifyAfter(grant, after)
        check(!equal(infoHex(before, "nonce", 16), infoHex(after, "nonce", 16)), "La verificación requiere una sesión BLE nueva.")
        check(integer(before, "partition") != integer(after, "partition"), "La R2 no cambió a la partición nueva.")
    }

    /** Checks snapshot coherence. Device identity is subsequently bound by a signed grant/server HMAC. */
    fun verifySnapshot(info: JSONObject) { verifiedInfo(null, info) }

    internal fun sessionManifest(grant: ByteArray, info: JSONObject, phonePublic: ByteArray, sign: (ByteArray) -> ByteArray): ByteArray {
        verifyBefore(grant, info)
        val data = verifyGrant(grant)
        check(equal(data.phonePub, phonePublic), "Este permiso offline pertenece a otro teléfono.")
        val message = SESSION_LABEL + decodeHex(data.uuid, 16) + infoHex(info, "nonce", 16) + sha256(grant)
        val signature = sign(message)
        check(verify(publicKey(phonePublic), message, signature), "El teléfono no pudo firmar la sesión offline.")
        return grant.copyOf() + signature
    }

    private data class InfoProof(val counter: Long, val digest: String, val lastGrant: String, val bootValid: Boolean, val fw: String)

    private fun verifiedInfo(data: GrantData?, info: JSONObject): InfoProof {
        check(integer(info, "offline_protocol") == 1L && integer(info, "ota_protocol") == 1L, "La R2 no admite el protocolo offline firmado.")
        val key = infoHex(info, "offline_public_key", 65)
        if (data != null) check(equal(key, data.devicePub), "La clave pública no corresponde a la R2 autorizada.")
        check(equal(infoHex(info, "offline_anchor_id", 8), anchorId), "La R2 utiliza otro firmante offline.")
        val name = string(info, "nombre")
        val hw = string(info, "hw")
        val fw = string(info, "fw")
        val mac = mac(string(info, "mac"))
        check(hw == "3.0" && name.matches(Regex("TQT[-_]R2[-_]V30[-_][0-9]{4}")), "La información offline no pertenece a una TQT R2 HW 3.0.")
        if (data != null) check(name == data.name && hw == data.hw && hex(mac) == data.mac.replace(":", ""), "La identidad física de la R2 no coincide con el permiso.")
        check(compatibleVersion(fw), "La R2 necesita firmware 4.3 o posterior para offline.")
        val counter = integer(info, "offline_counter")
        val partition = integer(info, "partition")
        val boot = info.opt("boot_valid") as? Boolean ?: fail("Estado de arranque offline inválido.")
        val digest = infoHex(info, "app_sha256", 32)
        val lastGrant = infoHex(info, "offline_last_grant", 16)
        val transcript = INFO_LABEL + infoHex(info, "nonce", 16) + digest + le32(counter) + le32(partition) +
            byteArrayOf(if (boot) 1 else 0) + padded(name, 24) + padded(hw, 8) + padded(fw, 16) + mac + lastGrant
        check(verify(publicKey(key), transcript, infoHex(info, "offline_signature", 64)), "La firma de información de la R2 es inválida.")
        return InfoProof(counter, hex(digest), hex(lastGrant), boot, fw)
    }

    companion object {
        const val GRANT_BYTES = 408
        const val SESSION_MANIFEST_BYTES = 472
        const val ROOT_ID = "09aaa3c70c9ca6f4"
        private const val UINT32_MAX = 0xffff_ffffL
        private const val ROOT_HEX = "04c837951d85559451a91334eeb62704c6c377a214b928d15ee5dd9ece9f279919842e8a6813e988c61bdb533cd15b321d64be3a9d29bf80e1377724f64983a2d1"
        private val MAGIC = decodeHex("5451542d4f46464c494e452d76310000", 16)
        internal val INFO_LABEL = "TQT-OFFLINE-INFO-v1".toByteArray(Charsets.US_ASCII)
        internal val SESSION_LABEL = "TQT-OFFLINE-SESSION-v1".toByteArray(Charsets.US_ASCII)
        private val parameters: ECParameterSpec by lazy {
            AlgorithmParameters.getInstance("EC").apply { init(ECGenParameterSpec("secp256r1")) }.getParameterSpec(ECParameterSpec::class.java)
        }
        private val production by lazy {
            val anchor = decodeHex(ROOT_HEX, 65)
            check(hex(sha256(anchor).copyOf(8)) == ROOT_ID, "El ancla pública offline está dañada.")
            OfflineCrypto(anchor)
        }

        fun verifyGrant(grant: ByteArray): GrantData = production.verifyGrant(grant)
        fun verifyBefore(grant: ByteArray, info: JSONObject) = production.verifyBefore(grant, info)
        fun verifyAfter(grant: ByteArray, info: JSONObject) = production.verifyAfter(grant, info)
        fun verifyAfter(grant: ByteArray, before: JSONObject, after: JSONObject) = production.verifyAfter(grant, before, after)
        fun verifySnapshot(info: JSONObject) = production.verifySnapshot(info)
        internal fun sessionManifest(grant: ByteArray, info: JSONObject, phonePublic: ByteArray, sign: (ByteArray) -> ByteArray) =
            production.sessionManifest(grant, info, phonePublic, sign)

        internal fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it.toInt() and 255) }
        internal fun decodeHex(value: String, bytes: Int): ByteArray {
            check(value.length == bytes * 2 && value.matches(Regex("[0-9a-fA-F]+")), "Campo hexadecimal offline inválido.")
            return ByteArray(bytes) { value.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
        }
        internal fun sha256(bytes: ByteArray): ByteArray = MessageDigest.getInstance("SHA-256").digest(bytes)
        private fun equal(a: ByteArray, b: ByteArray) = MessageDigest.isEqual(a, b)
        private fun check(condition: Boolean, message: String) { if (!condition) fail(message) }
        private fun fail(message: String): Nothing = throw OfflineVerificationException(message)
        private fun string(info: JSONObject, name: String) = info.opt(name) as? String ?: fail("Falta información offline válida de la R2.")
        private fun infoHex(info: JSONObject, field: String, size: Int) = decodeHex(string(info, field), size)
        private fun integer(info: JSONObject, field: String): Long {
            val value = when (val number = info.opt(field)) { is Int -> number.toLong(); is Long -> number; else -> fail("Contador o estado offline inválido.") }
            check(value in 0..UINT32_MAX, "Contador o estado offline fuera de rango.")
            return value
        }
        private fun mac(value: String): ByteArray {
            check(value.matches(Regex("[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}")), "Dirección MAC offline inválida.")
            return decodeHex(value.replace(":", ""), 6)
        }
        private fun asciiField(bytes: ByteArray, start: Int, size: Int): String {
            val field = bytes.copyOfRange(start, start + size)
            val end = field.indexOf(0)
            check(end > 0 && field.take(end).all { it.toInt() in 32..126 } && field.drop(end).all { it == 0.toByte() }, "Perfil offline con texto no canónico.")
            return String(field, 0, end, Charsets.US_ASCII)
        }
        internal fun padded(value: String, length: Int): ByteArray {
            check(value.isNotEmpty() && value.length < length && value.all { it.code in 32..126 }, "Perfil offline con texto inválido.")
            return value.toByteArray(Charsets.US_ASCII).copyOf(length)
        }
        private fun compatibleVersion(value: String): Boolean {
            if (!value.matches(Regex("(0|[1-9][0-9]*)(\\.(0|[1-9][0-9]*)){1,3}"))) return false
            val pieces = value.split('.').map { it.toLongOrNull() ?: return false }
            return pieces[0] > 4 || (pieces[0] == 4L && pieces[1] >= 3)
        }
        private fun u32(bytes: ByteArray, at: Int) = (0..3).fold(0L) { value, i -> value or ((bytes[at + i].toLong() and 255L) shl (8 * i)) }
        internal fun le32(value: Long): ByteArray {
            check(value in 0..UINT32_MAX, "Entero offline fuera de rango.")
            return ByteArray(4) { (value ushr (it * 8)).toByte() }
        }

        internal fun publicKey(bytes: ByteArray): PublicKey {
            check(bytes.size == 65 && bytes[0] == 4.toByte(), "Clave pública P-256 inválida.")
            val x = BigInteger(1, bytes.copyOfRange(1, 33))
            val y = BigInteger(1, bytes.copyOfRange(33, 65))
            val field = parameters.curve.field as java.security.spec.ECFieldFp
            val p = field.p
            check(x < p && y < p && y.modPow(BigInteger.valueOf(2), p) == (x.modPow(BigInteger.valueOf(3), p) + parameters.curve.a * x + parameters.curve.b).mod(p), "Punto público fuera de la curva P-256.")
            return KeyFactory.getInstance("EC").generatePublic(ECPublicKeySpec(ECPoint(x, y), parameters))
        }

        internal fun publicBytes(key: PublicKey): ByteArray {
            val ec = key as? ECPublicKey ?: fail("La clave del teléfono no es EC P-256.")
            check(ec.params.order == parameters.order && ec.params.curve == parameters.curve && ec.params.generator == parameters.generator, "La clave del teléfono utiliza otra curva.")
            val result = byteArrayOf(4) + unsigned32(ec.w.affineX) + unsigned32(ec.w.affineY)
            publicKey(result)
            return result
        }

        private fun verify(key: PublicKey, message: ByteArray, raw: ByteArray): Boolean = try {
            Signature.getInstance("SHA256withECDSA").run { initVerify(key); update(message); verify(rawToDer(raw)) }
        } catch (_: Exception) { false }

        /** Strict DER (minimal positive INTEGERs); rejects trailing, negative, zero and out-of-range scalars. */
        fun derToRaw(der: ByteArray): ByteArray {
            check(der.size in 8..72 && der[0] == 0x30.toByte() && (der[1].toInt() and 255) == der.size - 2, "Firma DER offline inválida.")
            var at = 2
            fun scalar(): ByteArray {
                check(at + 2 <= der.size && der[at++] == 2.toByte(), "Entero DER offline inválido.")
                val count = der[at++].toInt() and 255
                check(count in 1..33 && at + count <= der.size, "Longitud DER offline inválida.")
                val value = der.copyOfRange(at, at + count)
                at += count
                check((value[0].toInt() and 128) == 0 && !(count > 1 && value[0] == 0.toByte() && (value[1].toInt() and 128) == 0), "Entero DER offline no canónico.")
                val integer = BigInteger(1, value)
                check(integer.signum() > 0 && integer < parameters.order, "Escalar de firma offline inválido.")
                return unsigned32(integer)
            }
            val result = scalar() + scalar()
            check(at == der.size, "La firma DER contiene datos sobrantes.")
            return result
        }

        fun rawToDer(raw: ByteArray): ByteArray {
            check(raw.size == 64, "La firma offline debe tener 64 bytes.")
            fun scalar(start: Int): ByteArray {
                val value = BigInteger(1, raw.copyOfRange(start, start + 32))
                check(value.signum() > 0 && value < parameters.order, "Escalar de firma offline inválido.")
                val encoded = value.toByteArray()
                return byteArrayOf(2, encoded.size.toByte()) + encoded
            }
            val integers = scalar(0) + scalar(32)
            return byteArrayOf(0x30, integers.size.toByte()) + integers
        }

        private fun unsigned32(value: BigInteger): ByteArray {
            val encoded = value.toByteArray().dropWhile { it == 0.toByte() }.toByteArray()
            check(encoded.size <= 32, "Coordenada P-256 inválida.")
            return ByteArray(32 - encoded.size) + encoded
        }
    }
}
