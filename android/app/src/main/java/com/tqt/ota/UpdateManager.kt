package com.tqt.ota

import android.content.Intent
import android.util.Base64
import com.tqt.ota.ble.BleOtaTransport
import com.tqt.ota.ble.NearbyDevice
import com.tqt.ota.data.ApiFailure
import com.tqt.ota.data.PrivateStore
import com.tqt.ota.data.TqtApi
import com.tqt.ota.data.SessionContext
import com.tqt.ota.offline.OfflineCrypto
import com.tqt.ota.offline.OfflineKeys
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import java.util.UUID

data class ScreenState(
    val email: String = "", val role: String = "", val devices: List<JSONObject> = emptyList(),
    val nearby: List<NearbyDevice> = emptyList(), val history: List<JSONObject> = emptyList(),
    val firmwares: List<JSONObject> = emptyList(), val selected: JSONObject? = null,
    val packages: List<JSONObject> = emptyList(), val offlineSelected: String? = null,
    val busy: Boolean = false, val updating: Boolean = false, val stage: String = "Listo",
    val confirmed: Long = 0, val total: Long = 0, val error: String? = null, val release: JSONObject? = null
)

class UpdateManager(private val app: TqtApplication, private val store: PrivateStore, private val api: TqtApi) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutable = MutableStateFlow(ScreenState(email = store.email))
    val state: StateFlow<ScreenState> = mutable
    private val operation = Mutex()
    private val synchronization = Mutex()
    private var transferJob: Job? = null
    fun dismissError() { mutable.update { it.copy(error = null) } }
    private fun report(error: Exception) { mutable.update { it.copy(error = error.message?.take(320) ?: "No se pudo completar la operación", busy = false) } }
    private fun objects(value: JSONObject, key: String): List<JSONObject> = value.optJSONArray(key)?.let { array -> (0 until array.length()).map { array.getJSONObject(it) } } ?: emptyList()
    fun login(server: String, email: String, password: String) {
        if (state.value.updating) return
        mutable.update { it.copy(busy = true, error = null) }
        scope.launch {
            try {
                val user = api.login(server, email, password)
                if (user.optBoolean("debe_cambiar")) { store.logout(); throw IllegalStateException("Cambia primero la contraseña inicial en la web y vuelve a iniciar sesión.") }
                mutable.update { it.copy(email = user.getString("email"), role = user.optString("rol"), busy = false) }
                refreshNow(); app.scheduleSync()
            } catch (error: Exception) { report(error) }
        }
    }
    fun restore() { if (store.cookie.isNotEmpty() && !state.value.updating && !state.value.busy) scope.launch {
        val account = store.session()
        app.scheduleSync() // Durable retry is registered even when the initial network request fails.
        if (!state.value.updating) for (summary in store.records(account).filter { it.optString("state") == "preparing" }) {
            store.record(summary.getString("id"), account)?.let { store.save(it.put("state", "preparation_uncertain")) }
        }
        try {
            val user = api.request("/api/auth/yo", session = account)
            if (!store.matches(account)) return@launch
            mutable.update { it.copy(email = user.getString("email"), role = user.optString("rol")) }
            refreshNow(); app.scheduleSync()
        } catch (error: Exception) {
            if (!store.matches(account)) return@launch
            if (error is ApiFailure && error.status == 401 && !state.value.updating) { store.logout(); mutable.value = ScreenState(error = "Inicia sesión nuevamente; tus resultados siguen guardados.") }
            else { refreshHistory(); report(error) }
        }
    } }
    fun logout() {
        if (state.value.updating || state.value.busy) return
        scope.launch {
            runCatching { api.request("/api/auth/logout", JSONObject()) }
            store.logout(); mutable.value = ScreenState()
        }
    }
    fun refresh(query: String = "") { scope.launch { try { refreshNow(query) } catch (error: Exception) { report(error) } } }
    private suspend fun refreshNow(query: String = "") {
        val account = store.session()
        mutable.update { it.copy(busy = true) }
        val response = api.request("/api/android/devices?limit=100&q=" + java.net.URLEncoder.encode(query, "UTF-8"), session = account)
        if (!store.matches(account)) return
        mutable.update { it.copy(devices = objects(response, "items"), busy = false) }
        refreshHistory()
        runCatching { api.request("/api/android/apk/manifest", session = account) }.getOrNull()?.let { release -> if (store.matches(account)) mutable.update { it.copy(release = release) } }
    }
    fun select(device: JSONObject) {
        if (state.value.updating || state.value.busy) return
        mutable.update { it.copy(selected = device, nearby = emptyList(), firmwares = emptyList(), offlineSelected = null, error = null) }
        scope.launch {
            val account = store.session()
            try {
                val catalogue = api.request("/api/android/firmwares?hw=" + java.net.URLEncoder.encode(device.getString("hw"), "UTF-8"), session = account)
                // The generic 4.0 bootstrap is not a functional OTA target.
                val images = objects(catalogue, "items").filter { !it.optString("id").contains("generic") && it.optInt("ota_protocol") == 1 }
                if (store.matches(account) && state.value.selected?.optInt("pcb_id") == device.optInt("pcb_id")) mutable.update { it.copy(firmwares = images) }
            } catch (error: Exception) { report(error) }
        }
    }
    fun scan() {
        if (state.value.updating || state.value.busy) return
        mutable.update { it.copy(busy = true, error = null, stage = "Buscando R2 cercanas…") }
        scope.launch {
            val ble = BleOtaTransport(app)
            try { mutable.update { it.copy(nearby = ble.scan(), busy = false, stage = "Selecciona la tarjeta física") } }
            catch (error: Exception) { report(error) }
            finally { ble.close() }
        }
    }
    fun start(pcb: JSONObject, firmware: JSONObject, nearby: NearbyDevice) {
        if (state.value.updating || state.value.busy) return
        val account = store.session()
        val identifier = UUID.randomUUID().toString()
        val record = JSONObject().put("id", identifier).put("state", "preparing").put("pcb_id", pcb.getInt("pcb_id"))
            .put("nombre", pcb.getString("nombre")).put("firmware_id", firmware.getString("id")).put("address", nearby.address)
            .put("created", System.currentTimeMillis()).put("server", account.origin).put("operator", account.email)
        store.save(record)
        mutable.update { it.copy(updating = true, error = null) }
        try { app.startForegroundService(Intent(app, UpdateService::class.java).putExtra("operation", identifier)) }
        catch (error: Exception) { mutable.update { it.copy(updating = false) }; report(error) }
    }
    /** Prepare online, then preserve the opaque image and signed permission in private encrypted storage. */
    fun prepareOffline(pcb: JSONObject, firmware: JSONObject, nearby: NearbyDevice) {
        if (state.value.updating || state.value.busy) return
        val account = store.session()
        val id = UUID.randomUUID().toString()
        val record = JSONObject().put("id", id).put("state", "preparing").put("offline", true).put("kind", "offline")
            .put("pcb_id", pcb.getInt("pcb_id")).put("nombre", pcb.getString("nombre")).put("fw", firmware.getString("fw"))
            .put("firmware_id", firmware.getString("id")).put("address", nearby.address).put("created", System.currentTimeMillis())
            .put("server", account.origin).put("operator", account.email)
        store.save(record)
        mutable.update { it.copy(busy = true, error = null, stage = "Preparando autorización offline…") }
        scope.launch {
            operation.withLock {
                val ble = BleOtaTransport(app)
                try {
                    ble.connect(nearby.address)
                    val info = readyInfo(ble)
                    require(info.optInt("offline_protocol") == 1) { "Primero instala FW 4.3 online. La base genérica 4.0 conserva su alta inicial online." }
                    OfflineCrypto.verifySnapshot(info)
                    api.request("/api/android/offline/bind/${pcb.getInt("pcb_id")}", JSONObject().put("device", info), session = account)
                    val response = api.request("/api/android/offline/packages", JSONObject().put("client_operation_id", id)
                        .put("pcb_id", pcb.getInt("pcb_id")).put("firmware_id", firmware.getString("id"))
                        .put("phone_public_key", OfflineKeys().publicKeyHex()), session = account)
                    installOfflinePackage(record, response)
                    if (store.matches(account)) mutable.update { it.copy(stage = "Paquete offline autorizado y guardado") }
                } catch (error: Exception) {
                    record.put("state", "preparation_uncertain").put("error", error.message?.take(320)); store.save(record); report(error)
                } finally { ble.close(); mutable.update { it.copy(busy = false) }; refreshHistory() }
            }
        }
    }
    private fun installOfflinePackage(record: JSONObject, response: JSONObject) {
        val pkg = response.getJSONObject("package")
        val grant = Base64.decode(pkg.getString("grant"), Base64.DEFAULT)
        val data = OfflineCrypto.verifyGrant(grant)
        require(data.uuid == record.getString("id").replace("-", "") && response.getString("client_operation_id") == record.getString("id")) { "El permiso corresponde a otra operación." }
        require(data.name == record.getString("nombre") && OfflineKeys().publicKeyHex() == pkg.getString("phone_public_key")) { "El permiso pertenece a otra tarjeta o teléfono." }
        record.put("prepared", response).put("state", response.getString("state")).put("expires_at", response.getDouble("expires_at"))
            .put("receive_until", response.getDouble("receive_until")); store.save(record)
    }
    fun selectOffline(summary: JSONObject) {
        if (state.value.updating) return
        val record = store.record(summary.getString("id")) ?: return
        val pkg = record.getJSONObject("prepared").getJSONObject("package")
        mutable.update { it.copy(offlineSelected = record.getString("id"), selected = JSONObject().put("pcb_id", record.getInt("pcb_id"))
            .put("nombre", record.getString("nombre")).put("hw", pkg.getString("hw")), nearby = emptyList(),
            firmwares = listOf(JSONObject().put("id", record.getString("firmware_id")).put("fw", pkg.getString("fw")).put("hw", pkg.getString("hw"))), error = null) }
    }
    fun startOffline(identifier: String, nearby: NearbyDevice) {
        if (state.value.updating || state.value.busy) return
        try {
            val record = requireNotNull(store.record(identifier))
            require(record.optBoolean("offline") && record.getString("state") == "authorized") { "El permiso ya fue usado o requiere verificar la tarjeta." }
            require(System.currentTimeMillis() / 1000.0 < record.getDouble("expires_at")) { "El permiso caducó. Recupera conexión para preparar uno nuevo." }
            record.put("address", nearby.address); store.save(record)
            mutable.update { it.copy(updating = true, error = null) }
            app.startForegroundService(Intent(app, UpdateService::class.java).putExtra("operation", identifier))
        } catch (error: Exception) { mutable.update { it.copy(updating = false) }; report(error) }
    }
    fun runTransfer(identifier: String, completed: () -> Unit) {
        if (transferJob?.isActive == true) { completed(); return }
        transferJob = scope.launch {
            try { operation.withLock { withTimeout(20 * 60 * 1000L) { transfer(identifier) } } }
            catch (error: Exception) { report(error) }
            finally { mutable.update { it.copy(updating = false, busy = false) }; refreshHistory(); completed() }
        }
    }
    fun cancel() { transferJob?.cancel(CancellationException("Interrumpida por el operador; verificar el dispositivo antes de repetir.")) }
    private suspend fun readyInfo(ble: BleOtaTransport): JSONObject {
        repeat(100) {
            val info = ble.info()
            if (info.optBoolean("boot_valid")) return info
            delay(200)
        }
        throw IllegalStateException("El dispositivo aún no confirmó un arranque válido.")
    }
    private suspend fun reconnect(ble: BleOtaTransport, address: String): JSONObject {
        var last: Exception? = null
        repeat(20) {
            try { ble.connect(address); return readyInfo(ble) }
            catch (error: CancellationException) { throw error }
            catch (error: Exception) { last = error; ble.close(); delay(1500) }
        }
        throw IllegalStateException("Arranque pendiente de verificar. No repitas la instalación; usa Verificar dispositivo.", last)
    }
    private suspend fun transfer(identifier: String) {
        val account = store.session()
        val record = requireNotNull(store.record(identifier, account)) { "La operación pertenece a otra sesión o no está disponible." }
        if (record.optBoolean("offline")) { transferOffline(record, account); return }
        val ble = BleOtaTransport(app)
        mutable.update { it.copy(updating = true, error = null, confirmed = 0, total = 0, stage = "Conectando y verificando identidad…") }
        try {
            require(account.cookie.isNotEmpty() && record.getString("server") == account.origin && record.getString("operator") == account.email) { "Inicia sesión con el operador original." }
            ble.connect(record.getString("address"))
            var info = readyInfo(ble)
            if (info.optInt("enrollment") == 1) {
                mutable.update { it.copy(stage = "Autorizando el alta inicial online…") }
                val enrollment = api.request("/api/esp32/enroll/prepare/${record.getInt("pcb_id")}", JSONObject()
                    .put("firmware_id", record.getString("firmware_id")).put("device", info), session = account)
                record.put("enrollment_id", enrollment.getString("id")); store.save(record)
                ble.enroll(Base64.decode(enrollment.getString("ticket"), Base64.DEFAULT))
                info = readyInfo(ble)
                api.request("/api/esp32/enroll/result/${enrollment.getString("id")}", info, session = account)
            }
            record.put("before", info); store.save(record)
            mutable.update { it.copy(stage = "Autorizando firmware compatible…") }
            val response = api.request("/api/android/operations/prepare", JSONObject()
                .put("client_operation_id", identifier).put("pcb_id", record.getInt("pcb_id"))
                .put("firmware_id", record.getString("firmware_id")).put("device", info), session = account)
            val prepared = response.getJSONObject("prepared")
            val manifest = Base64.decode(prepared.getString("manifest"), Base64.DEFAULT)
            val encrypted = Base64.decode(prepared.getString("encrypted_image"), Base64.DEFAULT)
            require(manifest.size == 138 && encrypted.size == prepared.getInt("bytes") && encrypted.size in 1..0x140000) { "Paquete OTA incompleto o fuera de contrato." }
            record.put("prepared", response).put("state", "pending_verification").put("phase", "transferring")
            // Persist before BEGIN as well as COMMIT: any interruption is recoverable without reflashing.
            store.save(record)
            mutable.update { it.copy(stage = "Enviando por Bluetooth…", total = encrypted.size.toLong()) }
            ble.update(manifest, encrypted, progress = { acknowledged, total -> mutable.update { it.copy(confirmed = acknowledged, total = total) } }, beforeCommit = {
                record.put("phase", "commit_requested"); store.save(record)
            })
            mutable.update { it.copy(stage = "Reconectando para confirmar el nuevo arranque…") }
            val after = reconnect(ble, record.getString("address"))
            record.put("after", after).put("state", "pending_sync").put("phase", "boot_observed"); store.save(record)
            app.scheduleSync()
            submit(record, account)
            if (record.optString("state") == "migration_required") {
                require(!record.optBoolean("migration_attempt")) { "La transición de identidad requiere revisión; no se repetirá automáticamente." }
                val next = JSONObject(record.toString()).put("id", UUID.randomUUID().toString())
                    .put("parent_operation_id", identifier).put("migration_attempt", true).put("state", "preparing")
                    .put("created", System.currentTimeMillis())
                listOf("prepared", "after", "before", "server_result", "error").forEach { next.remove(it) }
                store.save(next); ble.close()
                try { transfer(next.getString("id")) } catch (error: Exception) { if (error !is CancellationException) report(error) }
            }
        } catch (error: Exception) {
            record.put("error", error.message?.take(320) ?: "Operación interrumpida")
            if (record.has("prepared") && record.optString("phase") !in listOf("commit_requested", "boot_observed")) {
                record.put("state", "pending_failure_sync").put("report", JSONObject()
                    .put("outcome", if (error is CancellationException) "cancelled" else "failed").put("error", record.getString("error")))
                store.save(record)
                withContext(NonCancellable) { runCatching { submit(record, account) } }
            } else {
                if (record.has("prepared")) record.put("state", if (record.has("after")) "pending_sync" else "pending_verification")
                else record.put("state", "preparation_uncertain")
                store.save(record)
            }
            app.scheduleSync()
            throw error
        } finally { ble.close() }
    }
    private suspend fun transferOffline(record: JSONObject, account: SessionContext) {
        val ble = BleOtaTransport(app)
        try {
            require(record.getString("state") == "authorized" && account.cookie.isNotEmpty()) { "El permiso requiere revisión con su operador original." }
            require(System.currentTimeMillis() / 1000.0 < record.getDouble("expires_at")) { "El permiso offline caducó." }
            val pkg = record.getJSONObject("prepared").getJSONObject("package")
            val grant = Base64.decode(pkg.getString("grant"), Base64.DEFAULT)
            val image = Base64.decode(pkg.getString("encrypted_image"), Base64.DEFAULT)
            val parsed = OfflineCrypto.verifyGrant(grant)
            require(image.size.toLong() == parsed.imageBytes && java.security.MessageDigest.getInstance("SHA-256").digest(image).joinToString("") { "%02x".format(it.toInt() and 255) } == pkg.getString("encrypted_sha256")) { "La imagen offline está incompleta o corrupta." }
            mutable.update { it.copy(updating = true, stage = "Verificando permiso y tarjeta sin Internet…", confirmed = 0, total = image.size.toLong()) }
            ble.connect(record.getString("address"))
            val before = readyInfo(ble)
            OfflineCrypto.verifyBefore(grant, before)
            val manifest = OfflineKeys().sessionManifest(grant, before)
            record.put("before", before).put("phone_signature", manifest.copyOfRange(408, 472).joinToString("") { "%02x".format(it.toInt() and 255) })
                .put("phase", "transferring").put("state", "pending_verification"); store.save(record)
            ble.offlineUpdate(manifest, image, progress = { received, total -> mutable.update { it.copy(confirmed = received, total = total, stage = "Enviando firmware offline…") } }, beforeCommit = {
                record.put("phase", "commit_requested"); store.save(record)
            })
            val after = reconnect(ble, record.getString("address"))
            OfflineCrypto.verifyAfter(grant, before, after)
            record.put("after", after).put("phase", "boot_observed").put("state", "pending_sync"); store.save(record)
            mutable.update { it.copy(stage = "Arranque firmado verificado · resultado guardado para sincronizar") }
            app.scheduleSync()
            runCatching { submit(record, account) } // Durable worker retries network failures; no reflash.
        } catch (error: Exception) {
            record.put("error", error.message?.take(320))
            if (record.optString("phase") !in listOf("commit_requested", "boot_observed")) {
                record.put("state", "authorized").put("attempts", record.optInt("attempts") + 1)
            } else record.put("state", if (record.has("after")) "pending_sync" else "pending_verification")
            store.save(record); app.scheduleSync(); throw error
        } finally { ble.close() }
    }
    private suspend fun submit(record: JSONObject, account: SessionContext) = synchronization.withLock { submitLocked(record, account) }
    private suspend fun submitLocked(record: JSONObject, account: SessionContext) {
        require(record.getString("server") == account.origin && record.getString("operator") == account.email) { "La sesión no corresponde al operador de esta evidencia." }
        val offline = record.optBoolean("offline")
        val body = record.optJSONObject("report") ?: if (offline) JSONObject().put("outcome", "verified")
            .put("before", record.getJSONObject("before")).put("after", record.getJSONObject("after")).put("phone_signature", record.getString("phone_signature"))
            else JSONObject().put("outcome", "verified").put("device", record.getJSONObject("after"))
        val path = if (offline) "/api/android/offline/operations/" else "/api/android/operations/"
        val response = api.request(path + record.getString("id") + "/result", body, session = account)
        val summary = JSONObject(response.toString()).apply { remove("prepared") }
        record.put("server_result", summary).put("state", response.getString("state")); store.save(record)
        if (store.matches(account)) mutable.update { it.copy(stage = if (record.getString("state") == "verified") "Actualización verificada y sincronizada" else "Resultado registrado: ${record.getString("state")}") }
    }
    fun verify(summary: JSONObject) {
        if (state.value.updating) return
        scope.launch {
            operation.withLock {
                val account = store.session()
                val record = store.record(summary.getString("id"), account) ?: return@withLock
                mutable.update { it.copy(busy = true, error = null, stage = "Leyendo el firmware realmente instalado…") }
                val ble = BleOtaTransport(app)
                try {
                    if (!record.has("prepared")) {
                        val path = if (record.optBoolean("offline")) "/api/android/offline/packages/" else "/api/android/operations/"
                        val known = api.request(path + record.getString("id"), session = account)
                        if (record.optBoolean("offline")) { installOfflinePackage(record, known); refreshHistory(); return@withLock }
                        if (known.has("prepared")) record.put("prepared", known)
                    }
                    val after = reconnect(ble, record.getString("address"))
                    if (record.optBoolean("offline")) {
                        val grant = Base64.decode(record.getJSONObject("prepared").getJSONObject("package").getString("grant"), Base64.DEFAULT)
                        if (runCatching { OfflineCrypto.verifyBefore(grant, after) }.isSuccess) {
                            // Fresh signed state proves no counter was consumed; retry remains an explicit user action.
                            record.put("state", "authorized")
                            listOf("before", "after", "phase", "phone_signature", "error").forEach { record.remove(it) }
                            store.save(record); mutable.update { it.copy(stage = "Permiso sin consumir: puedes reintentar explícitamente") }; return@withLock
                        }
                        OfflineCrypto.verifyAfter(grant, record.getJSONObject("before"), after)
                    }
                    record.put("after", after).put("state", "pending_sync"); store.save(record)
                    app.scheduleSync(); submit(record, account)
                } catch (error: Exception) {
                    if (error is ApiFailure && error.status in listOf(400, 404, 409, 422)) {
                        record.put("state", "pending_verification").put("error", error.message); store.save(record)
                    }
                    report(error); app.scheduleSync()
                }
                finally { ble.close(); mutable.update { it.copy(busy = false) }; refreshHistory() }
            }
        }
    }
    suspend fun synchronize(): Boolean = synchronization.withLock {
        val account = store.session()
        var complete = true
        for (summary in store.records(account).filter { it.optString("state") in listOf("pending_sync", "pending_failure_sync") }) {
            val record = store.record(summary.getString("id"), account) ?: continue
            try { submitLocked(record, account) } catch (error: Exception) {
                if (error is ApiFailure && error.status in listOf(400, 404, 409, 422)) {
                    record.put("state", "pending_verification").put("error", error.message); store.save(record)
                } else if (error is ApiFailure && error.status in listOf(401, 403)) {
                    mutable.update { it.copy(error = "Inicia sesión con el operador original para sincronizar los resultados.") }
                    break // Login explicitly reschedules; never loop on authorization errors.
                } else complete = false
            }
        }
        refreshHistory(); complete
    }
    fun synchronizeNow() { scope.launch { if (!synchronize()) mutable.update { it.copy(error = "Hay resultados pendientes. Comprueba la conexión o inicia sesión de nuevo.") }; app.scheduleSync() } }
    private fun refreshHistory() {
        val records = store.records()
        mutable.update { it.copy(history = records, packages = records.filter { row -> row.optBoolean("offline") && row.optString("state") == "authorized" }) }
    }
}
