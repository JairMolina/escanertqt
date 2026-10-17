@file:Suppress("DEPRECATION")

package com.tqt.ota.ble

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import android.os.SystemClock
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import com.tqt.ota.offline.OfflineCrypto
import com.tqt.ota.offline.OfflineVerificationException

data class NearbyDevice(val address: String, val name: String, val rssi: Int)

/** Activation may already have happened. Recover by reconnecting and checking INFO with the server. */
class OtaCommitPendingException(cause: Throwable? = null) : IOException(
    "Activación pendiente de verificar. Reconecta la R2 y comprueba su arranque antes de repetir OTA.", cause
)

/** Native GATT transport for the existing R2 protocol; never operates relay characteristics. */
@SuppressLint("MissingPermission")
class BleOtaTransport(context: Context) {
    private val appContext = context.applicationContext
    private val operations = Mutex()
    private val callbackLock = Any()
    @Volatile private var session: Session? = null
    @Volatile private var transferJob: Job? = null
    @Volatile private var scanJob: Job? = null

    private enum class Kind { CONNECT, DISCOVER, MTU, READ, WRITE, DESCRIPTOR }
    private data class Reply(val status: Int, val bytes: ByteArray = byteArrayOf(), val mtu: Int = 23)
    private class Pending(val kind: Kind, val uuid: UUID?, val result: CompletableDeferred<Reply>)
    private class GattFailure(val code: Int) : IOException("Bluetooth rechazó la operación GATT (código $code).")
    private class Session {
        var gatt: BluetoothGatt? = null
        @Volatile var connected = false
        @Volatile var pending: Pending? = null
        @Volatile var mtu = 23
        var info: BluetoothGattCharacteristic? = null
        var control: BluetoothGattCharacteristic? = null
        var data: BluetoothGattCharacteristic? = null
        var status: BluetoothGattCharacteristic? = null
        var offlineInfo: BluetoothGattCharacteristic? = null
        var notifications = false
        @Volatile var readFallback = false
        var lastInfo: JSONObject? = null
        val statuses = Channel<OtaProtocol.Status>(64)
        val disconnected = CompletableDeferred<Unit>()
    }

    private fun adapter(scan: Boolean = false): BluetoothAdapter {
        val permission = if (Build.VERSION.SDK_INT >= 31) {
            if (scan) Manifest.permission.BLUETOOTH_SCAN else Manifest.permission.BLUETOOTH_CONNECT
        } else if (scan) Manifest.permission.ACCESS_FINE_LOCATION else Manifest.permission.BLUETOOTH
        if (appContext.checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) {
            throw IOException("Concede el permiso de Bluetooth/dispositivos cercanos para continuar.")
        }
        if (Build.VERSION.SDK_INT >= 31 && appContext.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
            throw IOException("Concede el permiso de conexión Bluetooth para continuar.")
        }
        val result = appContext.getSystemService(BluetoothManager::class.java)?.adapter
            ?: throw IOException("Este Android no dispone de Bluetooth BLE.")
        if (!result.isEnabled) throw IOException("Activa Bluetooth para continuar.")
        return result
    }

    /** Names/services identify candidates only. The operator and authenticated API select identity. */
    suspend fun scan(durationMs: Long = 10000): List<NearbyDevice> = operations.withLock {
        require(durationMs in 1000..60000) { "Duración de búsqueda BLE inválida." }
        val scanner = adapter(scan = true).bluetoothLeScanner
            ?: throw IOException("Bluetooth BLE no está disponible.")
        val found = ConcurrentHashMap<String, NearbyDevice>()
        val failed = CompletableDeferred<Unit>()
        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val record = result.scanRecord
                val name = record?.deviceName.orEmpty()
                val otaService = record?.serviceUuids?.contains(ParcelUuid(SERVICE)) == true
                if (!name.startsWith("TQT", ignoreCase = true) && !otaService) return
                found[result.device.address] = NearbyDevice(result.device.address, name.ifBlank { "TQT (sin nombre)" }, result.rssi)
            }
            override fun onBatchScanResults(results: MutableList<ScanResult>) {
                results.forEach { onScanResult(ScanSettings.CALLBACK_TYPE_ALL_MATCHES, it) }
            }
            override fun onScanFailed(errorCode: Int) {
                failed.completeExceptionally(IOException("No se pudo buscar Bluetooth (código $errorCode)."))
            }
        }
        scanJob = currentCoroutineContext()[Job]
        try {
            scanner.startScan(null, ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), callback)
            withTimeoutOrNull(durationMs) { failed.await() }
        } finally {
            runCatching { scanner.stopScan(callback) }
            scanJob = null
        }
        found.values.sortedByDescending { it.rssi }
    }

    /** Connects only the explicit address selected by the operator. Rebuilds all GATT references. */
    suspend fun connect(address: String): Unit = operations.withLock {
        require(BluetoothAdapter.checkBluetoothAddress(address)) { "Dirección Bluetooth inválida." }
        val device = adapter().getRemoteDevice(address)
        closeSession(session)
        var last: Exception? = null
        repeat(2) { attempt ->
            currentCoroutineContext().ensureActive()
            val s = Session()
            session = s
            try {
                operation(s, Kind.CONNECT, timeout = 20000) {
                    val created = device.connectGatt(appContext, false, callbacks(s), BluetoothDevice.TRANSPORT_LE,
                        BluetoothDevice.PHY_LE_1M_MASK, Handler(Looper.getMainLooper()))
                    if (session !== s) {
                        created?.close()
                        false
                    } else {
                        s.gatt = created
                        created != null
                    }
                }
                // Use only the actual callback MTU. Android 14+ may negotiate 517 automatically.
                try {
                    val reply = operation(s, Kind.MTU) { s.gatt!!.requestMtu(517) }
                    s.mtu = reply.mtu.coerceIn(23, 517)
                } catch (_: GattFailure) {
                    s.mtu = 23
                }
                operation(s, Kind.DISCOVER) { s.gatt!!.discoverServices() }
                val service = s.gatt!!.getService(SERVICE)
                    ?: throw IOException("La tarjeta no expone el servicio OTA R2. Requiere una base compatible por USB.")
                s.info = service.getCharacteristic(INFO)
                s.control = service.getCharacteristic(CONTROL)
                s.data = service.getCharacteristic(DATA)
                s.status = service.getCharacteristic(STATUS)
                s.offlineInfo = service.getCharacteristic(OFFLINE_INFO)?.takeIf { has(it, BluetoothGattCharacteristic.PROPERTY_READ) }
                if (s.info == null || s.control == null || s.data == null || s.status == null ||
                    !has(s.info!!, BluetoothGattCharacteristic.PROPERTY_READ) ||
                    !has(s.status!!, BluetoothGattCharacteristic.PROPERTY_READ) ||
                    !has(s.control!!, BluetoothGattCharacteristic.PROPERTY_WRITE) ||
                    !has(s.data!!, BluetoothGattCharacteristic.PROPERTY_WRITE)) {
                    throw IOException("El servicio OTA R2 está incompleto o es incompatible.")
                }
                enableNotifications(s)
                s.gatt!!.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
                return@withLock
            } catch (cancelled: CancellationException) {
                closeSession(s)
                throw cancelled
            } catch (error: Exception) {
                last = error
                closeSession(s)
                if (attempt == 0) delay(500)
            }
        }
        throw IOException("No se pudo conectar la R2: ${last?.message.orEmpty()}", last)
    }

    suspend fun info(): JSONObject = operations.withLock { readInfo(connected()) }

    // Preserve existing trailing-lambda calls when adding the optional commit checkpoint.
    suspend fun update(manifest: ByteArray, encryptedImage: ByteArray, progress: (Long, Long) -> Unit): Unit =
        update(manifest, encryptedImage, progress, beforeCommit = {})

    /** Returns after activation acceptance, never after authenticated boot verification. */
    suspend fun update(
        manifest: ByteArray, encryptedImage: ByteArray, progress: (Long, Long) -> Unit,
        beforeCommit: () -> Unit = {}
    ): Unit = performUpdate(manifest, encryptedImage, progress, beforeCommit, offline = false)

    suspend fun offlineUpdate(sessionManifest: ByteArray, encryptedImage: ByteArray, progress: (Long, Long) -> Unit): Unit =
        offlineUpdate(sessionManifest, encryptedImage, progress, beforeCommit = {})

    suspend fun offlineUpdate(
        sessionManifest: ByteArray, encryptedImage: ByteArray, progress: (Long, Long) -> Unit,
        beforeCommit: () -> Unit = {}
    ): Unit = performUpdate(sessionManifest, encryptedImage, progress, beforeCommit, offline = true)

    private suspend fun performUpdate(
        manifest: ByteArray, encryptedImage: ByteArray, progress: (Long, Long) -> Unit,
        beforeCommit: () -> Unit, offline: Boolean
    ): Unit = operations.withLock {
        if (offline) OtaProtocol.validateOfflineUpdate(manifest, encryptedImage)
        else OtaProtocol.validateUpdate(manifest, encryptedImage)
        val s = connected()
        requireReadyInfo(s, enrollment = false)
        if (offline && s.lastInfo!!.optInt("offline_protocol", 0) != 1) {
            throw IOException("La R2 necesita firmware compatible con offline firmado.")
        }
        transferJob = currentCoroutineContext()[Job]
        var commitAttempted = false
        try {
            discardStatuses(s)
            write(s, s.control!!, byteArrayOf(if (offline) OtaProtocol.OFFLINE_BEGIN else OtaProtocol.BEGIN))
            waitStart(s, if (offline) OtaProtocol.State.OFFLINE_MANIFEST else OtaProtocol.State.MANIFEST, manifest.size.toLong())
            stream(s, manifest, if (offline) OtaProtocol.Phase.OFFLINE_MANIFEST else OtaProtocol.Phase.MANIFEST, encryptedImage.size.toLong()) { _, _ -> }
            progress(0, encryptedImage.size.toLong())
            stream(s, encryptedImage, OtaProtocol.Phase.IMAGE, progress = progress)
            // READY was checked by the acknowledgement tracker, including exact final length.
            // Persist the activation checkpoint before CONTROL2 can reach the device.
            beforeCommit()
            currentCoroutineContext().ensureActive()
            commitAttempted = true
            write(s, s.control!!, byteArrayOf(OtaProtocol.COMMIT))
            awaitRestart(s)
        } catch (error: Exception) {
            if (commitAttempted) {
                closeSession(s)
                throw OtaCommitPendingException(error)
            }
            bestEffortAbort(s)
            closeSession(s)
            throw error
        } finally {
            transferJob = null
        }
    }

    /** Online signed, session-bound ticket prepared by the server; contains no signing key here. */
    suspend fun enroll(ticket: ByteArray): Unit = operations.withLock {
        require(ticket.size == OtaProtocol.TICKET_SIZE) { "El ticket de alta debe tener 286 bytes." }
        val s = connected()
        requireReadyInfo(s, enrollment = true)
        transferJob = currentCoroutineContext()[Job]
        try {
            discardStatuses(s)
            write(s, s.control!!, byteArrayOf(OtaProtocol.ENROLL))
            waitStart(s, OtaProtocol.State.ENROLLMENT, OtaProtocol.TICKET_SIZE.toLong())
            stream(s, ticket, OtaProtocol.Phase.ENROLLMENT) { _, _ -> }
            // Enrollment changes identity in-place; the caller reads fresh INFO and validates it with the API.
            s.lastInfo = null
        } catch (error: Exception) {
            bestEffortAbort(s)
            closeSession(s)
            throw error
        } finally {
            transferJob = null
        }
    }

    suspend fun abort() {
        scanJob?.cancel(CancellationException("Búsqueda Bluetooth cancelada."))
        transferJob?.cancel(CancellationException("Actualización cancelada por el operador."))
        operations.withLock {
            val s = session ?: return@withLock
            bestEffortAbort(s)
            closeSession(s)
        }
    }

    fun close() {
        scanJob?.cancel(CancellationException("Búsqueda Bluetooth cerrada."))
        transferJob?.cancel(CancellationException("Conexión Bluetooth cerrada."))
        closeSession(session)
    }

    private fun connected(): Session = session?.takeIf { it.connected && it.gatt != null }
        ?: throw IOException("Conecta primero la R2 seleccionada.")

    private suspend fun readInfo(s: Session): JSONObject {
        repeat(3) { attempt ->
            val value = readJson(s, s.info!!)
            if (value.optInt("ota_protocol", 0) != 1 ||
                !Regex("^TQT[-_]R2[-_]", RegexOption.IGNORE_CASE).containsMatchIn(value.optString("nombre"))) {
                throw IOException("La tarjeta no es una TQT R2 con OTA v1 compatible.")
            }
            OtaProtocol.payloadSize(s.mtu, value.optInt("chunk", 16))
            val extra = s.offlineInfo
            if (extra != null) {
                val frame = OtaProtocol.decodeOfflineInfo(operation(s, Kind.READ, extra.uuid) { s.gatt!!.readCharacteristic(extra) }.bytes)
                value.put("offline_protocol", 1)
                    .put("offline_public_key", OfflineCrypto.hex(frame.devicePublicKey))
                    .put("offline_counter", frame.counter)
                    .put("offline_anchor_id", OfflineCrypto.hex(frame.anchorId))
                    .put("offline_identity_proof", OfflineCrypto.hex(frame.identityProof))
                    .put("offline_signature", OfflineCrypto.hex(frame.signature))
                    .put("offline_last_grant", OfflineCrypto.hex(frame.lastGrant))
                try { OfflineCrypto.verifySnapshot(value) } catch (error: OfflineVerificationException) {
                    if (attempt < 2) return@repeat // Re-read the entire pair; never mix snapshots.
                    throw IOException("La información offline de la R2 no tiene una firma coherente.", error)
                }
            }
            s.lastInfo = value
            return value
        }
        throw IOException("No se pudo leer una instantánea coherente de la R2.")
    }

    private suspend fun requireReadyInfo(s: Session, enrollment: Boolean) {
        val info = s.lastInfo ?: readInfo(s)
        if (!info.optBoolean("boot_valid", false)) throw IOException("Espera a que la R2 confirme su arranque y lee su información de nuevo.")
        if (enrollment != (info.optInt("enrollment", 0) == 1)) {
            throw IOException(if (enrollment) "La R2 no necesita o no admite alta genérica." else "Asigna primero la identidad de la R2 genérica.")
        }
    }

    private suspend fun stream(
        s: Session, bytes: ByteArray, phase: OtaProtocol.Phase, imageTotal: Long = 0,
        progress: (Long, Long) -> Unit
    ) {
        val chunk = OtaProtocol.payloadSize(s.mtu, s.lastInfo!!.optInt("chunk", 16))
        val acks = OtaProtocol.Acknowledgements(phase, bytes.size.toLong(), imageTotal)
        var firstWindow = true
        var reported = 0L
        while (!acks.complete) {
            currentCoroutineContext().ensureActive()
            val start = acks.confirmed.toInt()
            val fastCapable = s.notifications && !s.readFallback && has(s.data!!, BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE)
            // Confirm one safe response write before enabling the firmware's eight-packet window.
            val packets = if (firstWindow || !fastCapable) 1 else OtaProtocol.WINDOW
            val end = minOf(bytes.size, start + chunk * packets)
            var attempts = 0
            do {
                var offset = acks.confirmed.toInt()
                while (offset < end) {
                    currentCoroutineContext().ensureActive()
                    val length = minOf(chunk, end - offset)
                    acks.sentThrough(maxOf(acks.sent, (offset + length).toLong()))
                    write(s, s.data!!, OtaProtocol.packet(bytes, offset, length),
                        withoutResponse = fastCapable && !firstWindow)
                    offset += length
                }
                val deadline = SystemClock.elapsedRealtime() + ACK_TIMEOUT
                while (!acks.complete && SystemClock.elapsedRealtime() < deadline) {
                    val status = nextStatus(s)
                    acks.accept(status)
                    if (phase == OtaProtocol.Phase.IMAGE && acks.confirmed > reported) {
                        reported = acks.confirmed
                        progress(reported, bytes.size.toLong())
                    }
                    if (acks.confirmed >= end && (end < bytes.size || acks.complete)) break
                }
                if (acks.complete || (acks.confirmed >= end && end < bytes.size)) break
                // The firmware explicitly ignores duplicate offsets. Retry only unconfirmed bytes.
                // Final acceptance requires READY/RECEIVING/IDLE, not merely a full offset.
                if (++attempts >= 3) throw IOException("La R2 no confirmó el bloque OTA; no se activó el firmware.")
            } while (true)
            firstWindow = false
        }
    }

    private suspend fun waitStart(s: Session, state: OtaProtocol.State, total: Long) {
        val deadline = SystemClock.elapsedRealtime() + ACK_TIMEOUT
        while (SystemClock.elapsedRealtime() < deadline) {
            val status = nextStatus(s)
            rejectDeviceError(s, status)
            if (status.state == state) {
                if (status.offset != 0L || status.total != total) throw IOException("Inicio OTA fuera de secuencia.")
                return
            }
            if (status.state != OtaProtocol.State.IDLE) throw IOException("La R2 no está disponible para iniciar esta operación.")
        }
        throw IOException("La R2 no confirmó el inicio OTA.")
    }

    private suspend fun awaitRestart(s: Session) {
        val deadline = SystemClock.elapsedRealtime() + 8000
        var accepted = false
        while (SystemClock.elapsedRealtime() < deadline) {
            val queued = s.statuses.tryReceive().getOrNull()
            if (queued == null && !s.connected) {
                if (accepted) return
                throw OtaCommitPendingException()
            }
            val status = try { queued ?: nextStatus(s, notificationWait = 100) } catch (error: Exception) {
                if (accepted && !s.connected) return
                throw error
            }
            rejectDeviceError(s, status)
            if (status.state == OtaProtocol.State.RESTARTING) accepted = true
            else if (status.state != OtaProtocol.State.READY) throw OtaCommitPendingException()
            if (accepted && withTimeoutOrNull(800) { s.disconnected.await(); true } == true) return
        }
        if (!accepted) throw OtaCommitPendingException()
        // Some Android stacks retain a stale connection across ESP32 reset. Force fresh discovery next time.
        closeSession(s)
    }

    private fun discardStatuses(s: Session) {
        while (s.statuses.tryReceive().isSuccess) Unit
    }

    private suspend fun nextStatus(s: Session, notificationWait: Long = 150): OtaProtocol.Status {
        currentCoroutineContext().ensureActive()
        if (s.notifications && !s.readFallback) {
            val event = withTimeoutOrNull(notificationWait) { s.statuses.receive() }
            if (event != null) {
                rejectDeviceError(s, event)
                return event
            }
            // Use one status source from this point forward. A JSON read and an in-flight
            // notification can observe different instants; interleaving them would create
            // false regressive ACKs. A missing notification therefore selects safe READ mode.
            s.readFallback = true
            discardStatuses(s)
        }
        if (!s.connected) throw IOException("Bluetooth se desconectó durante OTA.")
        // JSON READ fallback also recovers a dropped notification; Android performs the ATT long read.
        val value = readJson(s, s.status!!)
        val stateName = value.opt("state") as? String ?: throw IOException("Estado OTA inválido.")
        val state = OtaProtocol.status(stateName, jsonInteger(value, "offset"),
            jsonInteger(value, "total"), value.optString("error").takeIf { it.isNotEmpty() })
        rejectDeviceError(s, state)
        if (!s.notifications || s.readFallback) delay(30)
        return state
    }

    private suspend fun rejectDeviceError(s: Session, status: OtaProtocol.Status) {
        if (status.state != OtaProtocol.State.ERROR && status.error == null) return
        val detail = if (s.connected && status.error == "device_error") {
            try { readJson(s, s.status!!).optString("error") } catch (_: IOException) { null }
        } else status.error
        throw IOException(OtaProtocol.deviceError(detail))
    }

    private suspend fun readJson(s: Session, characteristic: BluetoothGattCharacteristic): JSONObject {
        val bytes = operation(s, Kind.READ, characteristic.uuid) { s.gatt!!.readCharacteristic(characteristic) }.bytes
        try {
            if (bytes.isEmpty() || bytes.size > 512) throw IllegalArgumentException()
            val text = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString()
            return JSONObject(text)
        } catch (_: Exception) {
            // Never include INFO, proofs, nonce, ticket or image bytes in an error/log.
            throw IOException("La R2 respondió información OTA inválida o incompleta.")
        }
    }

    private fun jsonInteger(value: JSONObject, field: String): Long = when (val number = value.opt(field)) {
        is Int -> number.toLong()
        is Long -> number
        else -> throw IOException("Offset o longitud del ACK OTA inválidos.")
    }

    private suspend fun enableNotifications(s: Session) {
        val characteristic = s.status!!
        if (!has(characteristic, BluetoothGattCharacteristic.PROPERTY_NOTIFY)) return
        val descriptor = characteristic.getDescriptor(CCCD) ?: return
        if (!s.gatt!!.setCharacteristicNotification(characteristic, true)) return
        try {
            operation(s, Kind.DESCRIPTOR, descriptor.uuid) {
                if (Build.VERSION.SDK_INT >= 33) {
                    s.gatt!!.writeDescriptor(descriptor, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE) == BluetoothStatusCodes.SUCCESS
                } else {
                    descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    s.gatt!!.writeDescriptor(descriptor)
                }
            }
            s.notifications = true
        } catch (_: GattFailure) {
            s.gatt!!.setCharacteristicNotification(characteristic, false)
        }
    }

    private suspend fun write(s: Session, characteristic: BluetoothGattCharacteristic, bytes: ByteArray, withoutResponse: Boolean = false) {
        val type = if (withoutResponse) BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE else BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        operation(s, Kind.WRITE, characteristic.uuid) {
            if (Build.VERSION.SDK_INT >= 33) {
                s.gatt!!.writeCharacteristic(characteristic, bytes, type) == BluetoothStatusCodes.SUCCESS
            } else {
                characteristic.writeType = type
                characteristic.value = bytes
                s.gatt!!.writeCharacteristic(characteristic)
            }
        }
    }

    /** Only one Android GATT request may be outstanding. Timeout/cancel retires the whole session. */
    private suspend fun operation(
        s: Session, kind: Kind, uuid: UUID? = null, timeout: Long = IO_TIMEOUT, start: () -> Boolean
    ): Reply {
        currentCoroutineContext().ensureActive()
        val pending = Pending(kind, uuid, CompletableDeferred())
        synchronized(callbackLock) {
            if (session !== s || (kind != Kind.CONNECT && !s.connected)) throw IOException("Bluetooth se desconectó.")
            check(s.pending == null) { "Ya existe una operación GATT pendiente." }
            s.pending = pending
        }
        try {
            var started = false
            repeat(3) { attempt ->
                if (!started) {
                    started = start()
                    if (!started && attempt < 2) delay(60L * (attempt + 1))
                }
            }
            if (!started) throw IOException("Bluetooth no pudo iniciar la operación; vuelve a conectar la R2.")
            val result = withTimeout(timeout) { pending.result.await() }
            if (result.status != BluetoothGatt.GATT_SUCCESS) throw GattFailure(result.status)
            return result
        } catch (timeoutError: TimeoutCancellationException) {
            closeSession(s)
            throw IOException("Bluetooth no respondió a tiempo. Reconecta la R2.", timeoutError)
        } catch (cancelled: CancellationException) {
            closeSession(s)
            throw cancelled
        } finally {
            synchronized(callbackLock) { if (s.pending === pending) s.pending = null }
        }
    }

    private suspend fun bestEffortAbort(s: Session) = withContext(NonCancellable) {
        if (session === s && s.connected && s.control != null && s.pending == null) {
            try { withTimeout(3000) { write(s, s.control!!, byteArrayOf(OtaProtocol.ABORT)) } } catch (_: Exception) { /* disconnect aborts too */ }
        }
    }

    private fun finish(s: Session, kind: Kind, uuid: UUID? = null, reply: Reply) {
        synchronized(callbackLock) {
            if (session !== s) return
            s.pending?.takeIf { it.kind == kind && it.uuid == uuid }?.result?.complete(reply)
        }
    }

    private fun closeSession(s: Session?) {
        if (s == null) return
        val gatt = synchronized(callbackLock) {
            if (session === s) session = null
            s.connected = false
            s.pending?.result?.completeExceptionally(IOException("Bluetooth se desconectó."))
            s.disconnected.complete(Unit)
            s.statuses.close(IOException("Bluetooth se desconectó durante OTA."))
            s.gatt.also { s.gatt = null }
        }
        runCatching { gatt?.disconnect() }
        runCatching { gatt?.close() }
    }

    private fun callbacks(s: Session) = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            if (session !== s) return
            if (status == BluetoothGatt.GATT_SUCCESS && newState == BluetoothProfile.STATE_CONNECTED) {
                s.connected = true
                finish(s, Kind.CONNECT, reply = Reply(status))
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED || status != BluetoothGatt.GATT_SUCCESS) {
                closeSession(s)
            }
        }
        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) = finish(s, Kind.DISCOVER, reply = Reply(status))
        override fun onMtuChanged(gatt: BluetoothGatt, mtu: Int, status: Int) {
            if (status == BluetoothGatt.GATT_SUCCESS) s.mtu = mtu.coerceIn(23, 517)
            finish(s, Kind.MTU, reply = Reply(status, mtu = mtu))
        }
        override fun onCharacteristicRead(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray, status: Int) =
            finish(s, Kind.READ, characteristic.uuid, Reply(status, value.copyOf()))
        override fun onCharacteristicRead(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
            if (Build.VERSION.SDK_INT < 33) finish(s, Kind.READ, characteristic.uuid, Reply(status, characteristic.value?.copyOf() ?: byteArrayOf()))
        }
        override fun onCharacteristicWrite(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) =
            finish(s, Kind.WRITE, characteristic.uuid, Reply(status))
        override fun onDescriptorWrite(gatt: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) =
            finish(s, Kind.DESCRIPTOR, descriptor.uuid, Reply(status))
        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray) {
            notifyStatus(s, characteristic, value)
        }
        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
            if (Build.VERSION.SDK_INT < 33) notifyStatus(s, characteristic, characteristic.value?.copyOf() ?: byteArrayOf())
        }
        override fun onServiceChanged(gatt: BluetoothGatt) {
            // Fresh discovery is required after reset/firmware change; never keep stale characteristic handles.
            closeSession(s)
        }
    }

    private fun notifyStatus(s: Session, characteristic: BluetoothGattCharacteristic, value: ByteArray) {
        if (session !== s || characteristic.uuid != STATUS || s.readFallback) return
        try {
            if (s.statuses.trySend(OtaProtocol.decodeNotification(value)).isFailure) closeSession(s)
        } catch (error: OtaProtocol.ProtocolException) {
            s.statuses.close(IOException(error.message))
        }
    }

    private fun has(characteristic: BluetoothGattCharacteristic, property: Int) = characteristic.properties and property != 0

    private companion object {
        val SERVICE: UUID = UUID.fromString(OtaProtocol.SERVICE)
        val INFO: UUID = UUID.fromString(OtaProtocol.INFO)
        val CONTROL: UUID = UUID.fromString(OtaProtocol.CONTROL)
        val DATA: UUID = UUID.fromString(OtaProtocol.DATA)
        val STATUS: UUID = UUID.fromString(OtaProtocol.STATUS)
        val OFFLINE_INFO: UUID = UUID.fromString(OtaProtocol.OFFLINE_INFO)
        val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        const val IO_TIMEOUT = 10000L
        const val ACK_TIMEOUT = 5000L
    }
}
