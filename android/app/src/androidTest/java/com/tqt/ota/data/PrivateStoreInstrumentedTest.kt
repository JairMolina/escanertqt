package com.tqt.ota.data

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.RandomAccessFile
import java.security.MessageDigest
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class PrivateStoreInstrumentedTest {
    private lateinit var context: TestContext
    private lateinit var store: PrivateStore
    private lateinit var owner: SessionContext

    private class TestContext(base: Context) : ContextWrapper(base) {
        private val prefix = "private-store-test-${UUID.randomUUID()}"
        val root = File(base.cacheDir, prefix).apply { check(mkdirs()) }
        override fun getDatabasePath(name: String): File = File(root, name)
        override fun getNoBackupFilesDir(): File = File(root, "no-backup").apply { mkdirs() }
        override fun getSharedPreferences(name: String, mode: Int): SharedPreferences = baseContext.getSharedPreferences("$prefix-$name", mode)
        override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?): SQLiteDatabase =
            SQLiteDatabase.openOrCreateDatabase(getDatabasePath(name), factory)
        override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?, handler: DatabaseErrorHandler?): SQLiteDatabase =
            SQLiteDatabase.openDatabase(getDatabasePath(name).absolutePath, factory, SQLiteDatabase.CREATE_IF_NECESSARY, handler)
        override fun deleteDatabase(name: String): Boolean = SQLiteDatabase.deleteDatabase(getDatabasePath(name))
    }
    @Before fun setup() {
        context = TestContext(InstrumentationRegistry.getInstrumentation().targetContext)
        store = PrivateStore(context)
        owner = login("https://fixture-a.invalid", "operator-a@tqt.invalid")
    }
    @After fun cleanup() {
        store.close()
        check(context.root.canonicalFile.parentFile == context.baseContext.cacheDir.canonicalFile)
        context.root.deleteRecursively()
    }
    private fun login(origin: String, email: String): SessionContext {
        val attempt = store.beginLogin(origin)
        check(store.installCookie(attempt, "tqt_sesion=${UUID.randomUUID()}"))
        return store.finishLogin(attempt, email)
    }
    private fun record(large: Boolean = false): JSONObject {
        val value = JSONObject().put("id", UUID.randomUUID().toString()).put("state", "pending_sync")
            .put("server", owner.origin).put("operator", owner.email).put("nombre", "TQT-R2-V30-0067")
            .put("pcb_id", 67).put("firmware_id", "fixture-r2").put("created", 1L)
            .put("after", JSONObject().put("nonce", "fixture-evidence"))
        if (large) {
            val image = "A".repeat(1_650_000)
            val prepared = JSONObject().put("prepared", JSONObject().put("encrypted_image", image))
            value.put("prepared", prepared).put("server_result", JSONObject(prepared.toString()))
        }
        return value
    }
    private fun detailFile(id: String): File = store.readableDatabase.rawQuery("SELECT detail_file FROM outbox_records WHERE id=?", arrayOf(id)).use {
        assertTrue(it.moveToFirst())
        File(context.noBackupFilesDir, "tqt-outbox-v2/${it.getString(0)}")
    }

    @Test fun largeDetailNeverEntersCursorWindowAndSurvivesReopen() {
        val full = record(large = true)
        assertTrue(full.toString().length > 3_000_000)
        store.save(full)
        val summary = store.records(owner).single()
        assertTrue(summary.toString().length < 2048)
        assertFalse(summary.has("prepared"))
        assertFalse(summary.has("server_result"))
        assertTrue(summary.getBoolean("has_prepared"))
        assertTrue(summary.getBoolean("has_after"))
        assertThrows(IllegalArgumentException::class.java) { store.save(summary) }
        val digest = MessageDigest.getInstance("SHA-256").digest(full.toString().toByteArray())
        store.close()
        store = PrivateStore(context)
        val loaded = store.record(full.getString("id"), owner)!!
        assertArrayEquals(digest, MessageDigest.getInstance("SHA-256").digest(loaded.toString().toByteArray()))
        assertEquals("pending_sync", store.records(owner).single().getString("state"))
    }

    @Test fun immutableOwnerSurvivesAccountChangeDuringSaveAndCannotBeReassigned() {
        val full = record()
        store.save(full)
        val other = login("https://fixture-b.invalid", "operator-b@tqt.invalid")
        assertFalse(store.matches(owner))
        full.put("error", "Result arrived after account change")
        store.save(full)
        assertTrue(store.records(other).isEmpty())
        assertNull(store.record(full.getString("id"), other))
        assertEquals("Result arrived after account change", store.record(full.getString("id"), owner)!!.getString("error"))
        val forgedOwner = JSONObject(full.toString()).put("server", other.origin).put("operator", other.email)
        assertThrows(IllegalArgumentException::class.java) { store.save(forgedOwner) }
        assertEquals(1, store.records(owner).size)
        assertTrue(store.records(other).isEmpty())
    }

    @Test fun staleCookiesAndLoginAbortCannotReplaceANewerSession() {
        val other = login("https://fixture-b.invalid", "operator-b@tqt.invalid")
        assertFalse(store.installCookie(owner, "tqt_sesion=old-cookie"))
        store.abortLogin(owner)
        assertEquals(other, store.session())
        store.logout()
        assertFalse(store.matches(other))
        assertFalse(store.installCookie(other, "tqt_sesion=resurrected"))
        assertEquals("", store.session().cookie)
    }

    @Test fun tamperedOrOversizedDetailIsDeniedWithoutLosingSummary() {
        val full = record()
        store.save(full)
        val id = full.getString("id")
        val file = detailFile(id)
        val original = file.readBytes()
        RandomAccessFile(file, "rw").use { it.seek(20); it.write((original[20].toInt() xor 1) and 255) }
        assertThrows(IllegalArgumentException::class.java) { store.record(id, owner) }
        // Even changing the unkeyed file hash cannot bypass the GCM/AAD proof.
        store.writableDatabase.execSQL("UPDATE outbox_records SET detail_hash=? WHERE id=?",
            arrayOf(MessageDigest.getInstance("SHA-256").digest(file.readBytes()), id))
        assertThrows(Exception::class.java) { store.record(id, owner) }
        RandomAccessFile(file, "rw").use { it.setLength(17L * 1024 * 1024) }
        assertThrows(IllegalArgumentException::class.java) { store.record(id, owner) }
        assertEquals(id, store.records(owner).single().getString("id"))
    }

    @Test fun migrationReadsLegacyThreeMegabyteBlobInChunksAndPreservesOriginal() {
        val full = record(large = true)
        val id = full.getString("id")
        store.save(full)
        val encryptedLegacy = detailFile(id).readBytes()
        val scope = store.scope()
        store.close()
        assertTrue(context.deleteDatabase("tqt-private-outbox.db"))
        SQLiteDatabase.openOrCreateDatabase(context.getDatabasePath("tqt-private-outbox.db"), null).use { legacy ->
            legacy.execSQL("CREATE TABLE outbox(id TEXT PRIMARY KEY,scope TEXT NOT NULL,state TEXT NOT NULL,updated INTEGER NOT NULL,payload BLOB NOT NULL)")
            legacy.execSQL("CREATE TABLE cache(id TEXT PRIMARY KEY,payload BLOB NOT NULL)")
            legacy.execSQL("INSERT INTO outbox VALUES(?,?,?,?,?)", arrayOf(id, scope, "pending_sync", 1L, encryptedLegacy))
            legacy.version = 1
        }
        store = PrivateStore(context)
        assertEquals("pending_sync", store.records(owner).single().getString("state"))
        assertEquals(1_650_000, store.record(id, owner)!!.getJSONObject("prepared").getJSONObject("prepared").getString("encrypted_image").length)
        store.readableDatabase.rawQuery("SELECT length(payload) FROM outbox WHERE id=?", arrayOf(id)).use {
            assertTrue(it.moveToFirst()); assertEquals(encryptedLegacy.size.toLong(), it.getLong(0))
        }
        assertEquals(2, store.readableDatabase.version)
    }
}
