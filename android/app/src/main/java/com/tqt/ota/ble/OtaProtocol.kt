package com.tqt.ota.ble

/** Wire contract of TQT R2 OTA v1. Contains no Android or cryptographic keys. */
object OtaProtocol {
    const val SERVICE = "d45a0001-6a76-4e41-9f38-a7043f0ec069"
    const val INFO = "d45a0002-6a76-4e41-9f38-a7043f0ec069"
    const val CONTROL = "d45a0003-6a76-4e41-9f38-a7043f0ec069"
    const val DATA = "d45a0004-6a76-4e41-9f38-a7043f0ec069"
    const val STATUS = "d45a0005-6a76-4e41-9f38-a7043f0ec069"
    const val OFFLINE_INFO = "d45a0006-6a76-4e41-9f38-a7043f0ec069"
    const val BEGIN: Byte = 1
    const val COMMIT: Byte = 2
    const val ABORT: Byte = 3
    const val ENROLL: Byte = 4
    const val OFFLINE_BEGIN: Byte = 5
    const val MANIFEST_SIZE = 138
    const val OFFLINE_MANIFEST_SIZE = 472
    const val TICKET_SIZE = 286
    const val MAX_PAYLOAD = 500
    const val WINDOW = 8 // Exact firmware queue capacity, not an arbitrary throughput setting.

    enum class State(val wire: Int, val json: String) {
        IDLE(0, "idle"), MANIFEST(1, "manifest"), RECEIVING(2, "receiving"),
        READY(3, "ready"), RESTARTING(4, "restarting"), ERROR(5, "error"),
        ENROLLMENT(6, "enrollment"), OFFLINE_MANIFEST(7, "offline_manifest")
    }

    data class Status(val state: State, val offset: Long, val total: Long, val error: String? = null)
    enum class Phase { MANIFEST, IMAGE, ENROLLMENT, OFFLINE_MANIFEST }
    class ProtocolException(message: String) : IllegalStateException(message)
    data class OfflineInfo(
        val devicePublicKey: ByteArray, val counter: Long, val anchorId: ByteArray,
        val identityProof: ByteArray, val signature: ByteArray, val lastGrant: ByteArray
    )

    fun decodeOfflineInfo(bytes: ByteArray): OfflineInfo {
        if (bytes.size != 190 || bytes[0] != 1.toByte()) throw ProtocolException("Información offline binaria inválida.")
        return OfflineInfo(bytes.copyOfRange(1, 66), u32(bytes, 66), bytes.copyOfRange(70, 78),
            bytes.copyOfRange(78, 110), bytes.copyOfRange(110, 174), bytes.copyOfRange(174, 190))
    }

    fun payloadSize(mtu: Int, advertisedChunk: Int): Int {
        require(mtu in 23..517) { "MTU BLE inválido." }
        require(advertisedChunk in 1..MAX_PAYLOAD) { "Tamaño de bloque OTA inválido." }
        // ATT opcode + handle = 3; the OTA packet adds a 4-byte offset.
        return minOf(MAX_PAYLOAD, advertisedChunk, mtu - 7)
    }

    fun u32(bytes: ByteArray, at: Int): Long {
        require(at >= 0 && at <= bytes.size - 4)
        return (0..3).fold(0L) { value, i -> value or ((bytes[at + i].toLong() and 255L) shl (8 * i)) }
    }

    fun packet(bytes: ByteArray, offset: Int, length: Int): ByteArray {
        require(offset >= 0 && length in 1..MAX_PAYLOAD && offset <= bytes.size - length)
        return ByteArray(length + 4).also { result ->
            for (i in 0..3) result[i] = (offset.toLong() ushr (8 * i)).toByte()
            bytes.copyInto(result, 4, offset, offset + length)
        }
    }

    fun decodeNotification(bytes: ByteArray): Status {
        if (bytes.size != 10) throw ProtocolException("ACK OTA inválido: se esperaban 10 bytes.")
        val state = State.entries.firstOrNull { it.wire == (bytes[0].toInt() and 255) }
            ?: throw ProtocolException("Estado OTA desconocido.")
        val flag = bytes[9].toInt() and 255
        if (flag !in 0..1 || (flag == 1 && state != State.ERROR)) {
            throw ProtocolException("Indicador de error OTA inválido.")
        }
        return status(state.json, u32(bytes, 1), u32(bytes, 5), if (flag == 1) "device_error" else null)
    }

    fun status(state: String, offset: Long, total: Long, error: String? = null): Status {
        val decoded = State.entries.firstOrNull { it.json == state }
            ?: throw ProtocolException("Estado OTA desconocido.")
        if (offset !in 0..0xffff_ffffL || total !in 0..0xffff_ffffL || offset > total) {
            throw ProtocolException("Offset o longitud del ACK OTA inválidos.")
        }
        val code = error?.takeIf { it.isNotEmpty() }
        if (decoded != State.ERROR && code != null) throw ProtocolException("ACK OTA con error incoherente.")
        return Status(decoded, offset, total, code)
    }

    fun validateUpdate(manifest: ByteArray, encryptedImage: ByteArray) {
        require(manifest.size == MANIFEST_SIZE) { "El manifiesto OTA v1 debe tener 138 bytes." }
        require(encryptedImage.size >= 65536 && u32(manifest, 48) == encryptedImage.size.toLong()) {
            "La imagen cifrada no coincide con la longitud del manifiesto."
        }
    }

    fun validateOfflineUpdate(manifest: ByteArray, encryptedImage: ByteArray) {
        require(manifest.size == OFFLINE_MANIFEST_SIZE) { "El manifiesto offline v1 debe tener 472 bytes." }
        require(encryptedImage.size >= 65536 && u32(manifest, 278) == encryptedImage.size.toLong()) {
            "La imagen cifrada no coincide con la longitud del permiso offline."
        }
    }

    /** Verifies device acknowledgements, including the manifest -> image offset reset. */
    class Acknowledgements(val phase: Phase, val total: Long, private val imageTotal: Long = 0) {
        var confirmed: Long = 0
            private set
        var sent: Long = 0
            private set
        var complete: Boolean = false
            private set

        init {
            require(total in 1..0xffff_ffffL)
            if (phase == Phase.MANIFEST) require(total == MANIFEST_SIZE.toLong() && imageTotal > 0)
            if (phase == Phase.OFFLINE_MANIFEST) require(total == OFFLINE_MANIFEST_SIZE.toLong() && imageTotal > 0)
            if (phase == Phase.ENROLLMENT) require(total == TICKET_SIZE.toLong())
        }

        fun sentThrough(offset: Long) {
            if (offset < sent || offset > total) throw ProtocolException("Secuencia de envío OTA inválida.")
            sent = offset
        }

        fun accept(status: Status): Long {
            if (status.state == State.ERROR || status.error != null) {
                throw ProtocolException(deviceError(status.error))
            }
            when (phase) {
                Phase.MANIFEST, Phase.OFFLINE_MANIFEST -> {
                    if (status.state == State.RECEIVING) {
                        if (sent != total || status.offset != 0L || status.total != imageTotal) invalid()
                        confirmed = total
                        complete = true
                        return confirmed
                    }
                    val expected = if (phase == Phase.MANIFEST) State.MANIFEST else State.OFFLINE_MANIFEST
                    if (status.state != expected || complete) invalid()
                }
                Phase.IMAGE -> {
                    if (status.state != State.RECEIVING && status.state != State.READY) invalid()
                    if (complete && status.state != State.READY) invalid()
                    if (status.state == State.READY && status.offset != total) invalid()
                }
                Phase.ENROLLMENT -> {
                    if (status.state != State.ENROLLMENT && status.state != State.IDLE) invalid()
                    if (complete && status.state != State.IDLE) invalid()
                    if (status.state == State.IDLE && (sent != total || status.offset != total)) invalid()
                }
            }
            if (status.total != total || status.offset < confirmed || status.offset > sent) invalid()
            confirmed = status.offset
            complete = when (phase) {
                Phase.MANIFEST, Phase.OFFLINE_MANIFEST -> false // Only the authenticated transition proves manifest acceptance.
                Phase.IMAGE -> status.state == State.READY
                Phase.ENROLLMENT -> status.state == State.IDLE
            }
            return confirmed
        }

        private fun invalid(): Nothing = throw ProtocolException("ACK OTA fuera de secuencia; no se confirmó el bloque.")
    }

    fun deviceError(code: String?): String = when (code) {
        "busy_or_not_provisioned" -> "La R2 está ocupada, sin credencial o aún no confirmó su arranque."
        "authorization_failed" -> "La R2 rechazó la autorización del firmware. Prepara una sesión nueva."
        "enrollment_not_available" -> "Esta R2 no permite el alta genérica en su estado actual."
        "enrollment_failed" -> "La R2 rechazó el ticket de alta. Prepara una sesión nueva."
        "queue_or_packet" -> "La R2 rechazó un bloque o su cola BLE se llenó."
        "offset_or_size" -> "La R2 rechazó la secuencia o longitud del firmware."
        "hash_or_profile_failed", "image_invalid" -> "La R2 rechazó la integridad o el perfil de la imagen."
        "write_failed" -> "La R2 no pudo escribir el firmware."
        "commit_failed" -> "La R2 no pudo activar la partición nueva."
        "timeout" -> "La R2 canceló OTA por falta de datos."
        "disconnected" -> "Bluetooth se desconectó durante OTA."
        else -> "La R2 detuvo la operación OTA."
    }
}
