package com.tqt.ota.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import android.util.Base64
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.security.KeyStore
import java.security.MessageDigest
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

data class SessionContext(val origin: String, val email: String, val cookie: String, val generation: Long) {
    override fun toString(): String = "SessionContext(origin=$origin,generation=$generation,cookie=<private>)"
}
class SessionChangedException : IOException("La sesión cambió; vuelve a abrir esta operación con el operador original.")

/** Small encrypted summaries in SQLite; full records in private encrypted atomic files. */
class PrivateStore(context: Context) : SQLiteOpenHelper(context, "tqt-private-outbox.db", null, 2) {
    private val preferences = context.getSharedPreferences("tqt-session", Context.MODE_PRIVATE)
    private val sessionLock = Any()
    private val directory = File(context.noBackupFilesDir, "tqt-outbox-v2").apply {
        check(isDirectory || mkdirs()) { "No se pudo abrir el almacenamiento privado." }
    }
    private val key: SecretKey by lazy {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey("tqt-outbox-v1", null) as? SecretKey) ?: KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder("tqt-outbox-v1", KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    override fun onCreate(db: SQLiteDatabase) {
        createRecords(db)
        db.execSQL("CREATE TABLE cache(id TEXT PRIMARY KEY,payload BLOB NOT NULL)")
    }
    private fun createRecords(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE IF NOT EXISTS outbox_records(id TEXT PRIMARY KEY,scope TEXT NOT NULL,state TEXT NOT NULL,updated INTEGER NOT NULL,summary BLOB NOT NULL,detail_file TEXT NOT NULL,detail_hash BLOB NOT NULL)")
        db.execSQL("CREATE INDEX IF NOT EXISTS outbox_records_scope ON outbox_records(scope,updated)")
    }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        require(oldVersion == 1 && newVersion == 2) { "Versión de almacenamiento privado incompatible." }
        createRecords(db)
        // Keep the original v1 rows unchanged for recovery. Read large BLOBs in
        // bounded chunks: even the legacy fixture may exceed a CursorWindow.
        val old = db.rawQuery("SELECT id,scope,updated,length(payload) FROM outbox", null).use { cursor ->
            buildList { while (cursor.moveToNext()) add(Legacy(cursor.getString(0), cursor.getString(1), cursor.getLong(2), cursor.getLong(3))) }
        }
        for (row in old) {
            require(row.size in 28..MAX_FILE_BYTES.toLong()) { "Registro anterior demasiado grande o incompleto." }
            val bytes = ByteArrayOutputStream(row.size.toInt())
            var position = 1
            while (bytes.size() < row.size) {
                val chunk = db.rawQuery("SELECT substr(payload,?,?) FROM outbox WHERE id=?", arrayOf(position.toString(), CHUNK_BYTES.toString(), row.id)).use {
                    check(it.moveToFirst()) { "Falta el registro anterior." }; it.getBlob(0)
                }
                require(chunk.isNotEmpty() && chunk.size <= CHUNK_BYTES) { "Registro anterior incompleto." }
                bytes.write(chunk); position += chunk.size
            }
            val record = JSONObject(decrypt(bytes.toByteArray(), "${row.scope}|${row.id}"))
            require(recordScope(record) == row.scope && record.getString("id") == row.id) { "El propietario del registro anterior no coincide." }
            saveInto(db, record, row.updated)
        }
    }
    private data class Legacy(val id: String, val scope: String, val updated: Long, val size: Long)
    private fun encrypt(text: String, aad: String): ByteArray {
        val raw = text.toByteArray(Charsets.UTF_8)
        require(raw.size <= MAX_DETAIL_BYTES) { "Registro privado demasiado grande." }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key); updateAAD(aad.toByteArray(Charsets.UTF_8)) }
        return cipher.iv + cipher.doFinal(raw)
    }
    private fun decrypt(raw: ByteArray, aad: String): String {
        require(raw.size in 28..MAX_FILE_BYTES) { "Registro privado incompleto o demasiado grande." }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, raw.copyOfRange(0, 12))); updateAAD(aad.toByteArray(Charsets.UTF_8))
        }
        return cipher.doFinal(raw.copyOfRange(12, raw.size)).toString(Charsets.UTF_8)
    }
    private fun committed(editor: android.content.SharedPreferences.Editor) {
        check(editor.commit()) { "No se pudo guardar la sesión privada." }
    }
    private fun generation() = preferences.getLong("generation", 0)
    private fun origin() = preferences.getString("server", DEFAULT_ORIGIN)!!
    private fun user() = preferences.getString("user", "")!!
    private fun savedCookie() = preferences.getString("cookie", null)?.let {
        decrypt(Base64.decode(it, Base64.NO_WRAP), "session|${origin()}")
    } ?: ""
    private fun encodedCookie(value: String, origin: String): String {
        require(value.length <= 2048 && Regex("^tqt_sesion=[A-Za-z0-9_.-]+$").matches(value)) { "Cookie de sesión inválida." }
        return Base64.encodeToString(encrypt(value, "session|$origin"), Base64.NO_WRAP)
    }
    fun session(): SessionContext = synchronized(sessionLock) { SessionContext(origin(), user(), savedCookie(), generation()) }
    fun matches(session: SessionContext): Boolean = synchronized(sessionLock) {
        generation() == session.generation && origin() == session.origin && user() == session.email
    }
    var baseUrl: String
        get() = synchronized(sessionLock) { origin() }
        set(value) = synchronized(sessionLock) {
            committed(preferences.edit().putString("server", TqtApi.validatedOrigin(value)).putString("user", "").remove("cookie").putLong("generation", generation() + 1))
        }
    var email: String
        get() = synchronized(sessionLock) { user() }
        set(value) = synchronized(sessionLock) {
            committed(preferences.edit().putString("user", value).remove("cookie").putLong("generation", generation() + 1))
        }
    var cookie: String
        get() = synchronized(sessionLock) { savedCookie() }
        set(value) = synchronized(sessionLock) {
            val editor = preferences.edit().putLong("generation", generation() + 1)
            if (value.isEmpty()) editor.remove("cookie") else editor.putString("cookie", encodedCookie(value, origin()))
            committed(editor)
        }
    fun beginLogin(server: String): SessionContext = synchronized(sessionLock) {
        committed(preferences.edit().putString("server", TqtApi.validatedOrigin(server)).putString("user", "").remove("cookie").putLong("generation", generation() + 1))
        session()
    }
    fun installCookie(expected: SessionContext, value: String): Boolean = synchronized(sessionLock) {
        if (!matches(expected)) return@synchronized false
        val editor = preferences.edit()
        if (value == "tqt_sesion=" || value == "tqt_sesion=\"\"") editor.remove("cookie")
        else editor.putString("cookie", encodedCookie(value, expected.origin))
        committed(editor)
        true
    }
    fun finishLogin(expected: SessionContext, email: String): SessionContext = synchronized(sessionLock) {
        if (!matches(expected)) throw SessionChangedException()
        require(savedCookie().isNotEmpty() && email.isNotBlank()) { "El servidor no emitió una sesión válida." }
        committed(preferences.edit().putString("user", email).putLong("generation", generation() + 1))
        session()
    }
    fun abortLogin(expected: SessionContext) = synchronized(sessionLock) { if (matches(expected)) logout() }
    fun logout() = synchronized(sessionLock) {
        committed(preferences.edit().remove("cookie").putString("user", "").putLong("generation", generation() + 1))
    }
    private fun scope(origin: String, email: String): String = MessageDigest.getInstance("SHA-256")
        .digest("$origin|$email".toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    fun scope(): String = session().let { scope(it.origin, it.email) }
    private fun recordScope(record: JSONObject): String {
        val origin = record.getString("server")
        require(TqtApi.validatedOrigin(origin) == origin && record.getString("operator").isNotBlank()) { "Registro sin propietario y servidor inmutables." }
        return scope(origin, record.getString("operator"))
    }
    private fun identifier(value: String): String {
        require(UUID.fromString(value).toString() == value) { "Identificador privado inválido." }
        return value
    }
    private fun summary(record: JSONObject): JSONObject {
        val value = JSONObject()
        for (field in SUMMARY_FIELDS) if (record.has(field)) value.put(field, record.get(field))
        value.put("_summary", true).put("has_prepared", record.has("prepared")).put("has_after", record.has("after"))
        require(value.toString().toByteArray(Charsets.UTF_8).size <= MAX_SUMMARY_BYTES) { "Resumen privado demasiado grande." }
        return value
    }
    @Synchronized fun save(record: JSONObject) {
        require(!record.optBoolean("_summary")) { "Carga el detalle completo antes de modificar una operación." }
        val db = writableDatabase
        db.beginTransaction()
        var previous: String? = null
        var committed = false
        try { previous = saveInto(db, record, System.currentTimeMillis()); db.setTransactionSuccessful(); committed = true }
        finally { db.endTransaction() }
        if (committed) previous?.let { AtomicFile(File(directory, it)).delete() }
    }
    private fun saveInto(db: SQLiteDatabase, record: JSONObject, updated: Long): String? {
        val id = identifier(record.getString("id"))
        val owner = recordScope(record)
        val previous = db.rawQuery("SELECT scope,detail_file FROM outbox_records WHERE id=?", arrayOf(id)).use {
            if (it.moveToFirst()) Pair(it.getString(0), it.getString(1)) else null
        }
        require(previous == null || previous.first == owner) { "El UUID ya pertenece a otro operador o servidor." }
        if (previous != null) require(Regex("$owner-$id-[a-f0-9-]{36}\\.bin").matches(previous.second) &&
            File(directory, previous.second).canonicalFile.parentFile == directory.canonicalFile) { "Ruta privada anterior inválida." }
        val detail = encrypt(record.toString(), "$owner|$id")
        val fileName = "$owner-$id-${UUID.randomUUID()}.bin"
        val atomic = AtomicFile(File(directory, fileName))
        val output = atomic.startWrite()
        try { output.write(detail); atomic.finishWrite(output) }
        catch (error: Exception) { atomic.failWrite(output); throw error }
        val values = ContentValues().apply {
            put("id", id); put("scope", owner); put("state", record.getString("state")); put("updated", updated)
            put("summary", encrypt(summary(record).toString(), "$owner|$id|summary")); put("detail_file", fileName)
            put("detail_hash", MessageDigest.getInstance("SHA-256").digest(detail))
        }
        // A new immutable file precedes the SQLite commit. An interruption
        // preserves either the previous complete record or the new complete one.
        check(db.insertWithOnConflict("outbox_records", null, values, SQLiteDatabase.CONFLICT_REPLACE) != -1L) { "No se pudo guardar la operación." }
        return previous?.second
    }
    @Synchronized fun records(session: SessionContext = session()): List<JSONObject> {
        val current = scope(session.origin, session.email)
        return readableDatabase.query("outbox_records", arrayOf("id", "summary"), "scope=?", arrayOf(current), null, null, "updated DESC").use { cursor ->
            buildList { while (cursor.moveToNext()) add(JSONObject(decrypt(cursor.getBlob(1), "$current|${cursor.getString(0)}|summary"))) }
        }
    }
    @Synchronized fun record(id: String, session: SessionContext = session()): JSONObject? {
        identifier(id)
        val owner = scope(session.origin, session.email)
        return readableDatabase.rawQuery("SELECT detail_file,detail_hash FROM outbox_records WHERE id=? AND scope=?", arrayOf(id, owner)).use { cursor ->
            if (!cursor.moveToFirst()) return@use null
            val name = cursor.getString(0)
            require(Regex("$owner-$id-[a-f0-9-]{36}\\.bin").matches(name)) { "Ruta privada inválida." }
            val file = File(directory, name)
            require(file.canonicalFile.parentFile == directory.canonicalFile && file.length() in 28..MAX_FILE_BYTES.toLong()) { "Detalle privado incompleto o demasiado grande." }
            val bytes = file.inputStream().use { input ->
                val buffer = ByteArray(64 * 1024)
                val output = ByteArrayOutputStream()
                while (true) {
                    val size = input.read(buffer)
                    if (size < 0) break
                    require(output.size() + size <= MAX_FILE_BYTES) { "Detalle privado demasiado grande." }
                    output.write(buffer, 0, size)
                }
                output.toByteArray()
            }
            require(MessageDigest.isEqual(MessageDigest.getInstance("SHA-256").digest(bytes), cursor.getBlob(1))) { "La integridad del detalle privado no coincide." }
            JSONObject(decrypt(bytes, "$owner|$id")).also {
                require(it.getString("id") == id && recordScope(it) == owner && !it.optBoolean("_summary")) { "Identidad privada distinta." }
            }
        }
    }
    fun cache(name: String, value: JSONObject) {
        val id = "${scope()}|$name"
        val text = value.toString()
        require(text.toByteArray(Charsets.UTF_8).size <= MAX_SUMMARY_BYTES) { "Caché demasiado grande." }
        writableDatabase.insertWithOnConflict("cache", null, ContentValues().apply { put("id", id); put("payload", encrypt(text, id)) }, SQLiteDatabase.CONFLICT_REPLACE)
    }
    fun cached(name: String): JSONObject? {
        val id = "${scope()}|$name"
        return readableDatabase.rawQuery("SELECT payload FROM cache WHERE id=?", arrayOf(id)).use { if (it.moveToFirst()) JSONObject(decrypt(it.getBlob(0), id)) else null }
    }
    private companion object {
        const val DEFAULT_ORIGIN = "https://inventariotqt.site"
        const val MAX_DETAIL_BYTES = 16 * 1024 * 1024
        const val MAX_FILE_BYTES = MAX_DETAIL_BYTES + 28
        const val MAX_SUMMARY_BYTES = 32 * 1024
        const val CHUNK_BYTES = 64 * 1024
        val SUMMARY_FIELDS = listOf("id", "server", "operator", "state", "pcb_id", "nombre", "firmware_id", "address", "created", "error", "parent_operation_id", "migration_attempt", "offline", "kind", "expires_at", "receive_until", "fw", "phase", "attempts")
    }
}
