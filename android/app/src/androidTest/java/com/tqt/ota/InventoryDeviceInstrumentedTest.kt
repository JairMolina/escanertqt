package com.tqt.ota

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.flow.first
import org.junit.Test
import org.junit.Assert.*
import com.tqt.ota.data.ApiFailure
import com.tqt.ota.data.InventoryClient
import com.tqt.ota.data.InventoryQuery
import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.MultiFormatReader
import com.google.zxing.RGBLuminanceSource
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.qrcode.QRCodeWriter

/** Explicitly opted-in, GET-only checks using the session already on the USB phone.
 * Does not export cookies, credentials or inventory, or change the user's session. */
class InventoryDeviceInstrumentedTest {
    private fun connectedApp(): TqtApplication {
        org.junit.Assume.assumeTrue(InstrumentationRegistry.getArguments().getString("readOnlyServer") == "true")
        val app = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as TqtApplication
        assertTrue("Sign in on the phone first", app.store.session().email.isNotEmpty())
        return app
    }
    @Test fun authenticatedServerReadOnly() = runBlocking {
        org.junit.Assume.assumeTrue(InstrumentationRegistry.getArguments().getString("readOnlyServer") == "true")
        val app = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as TqtApplication
        assertTrue("Sign in on the phone first", app.store.session().email.isNotEmpty())
        for (path in listOf("/api/health", "/api/android/devices?limit=1", "/api/pcb?tipo=R2&q=0011&limit=1", "/api/esp32/r2/status")) {
            try {
                val value = app.api.request(path)
                println("TQT_READ_ONLY $path status=200 total=${value.optInt("total", -1)} items=${value.optJSONArray("items")?.length() ?: -1} version=${value.optString("version")}")
            } catch (error: ApiFailure) { println("TQT_READ_ONLY $path status=${error.status}") }
        }
    }
    @Test fun numberElevenAndSimulatedQrResolveToSameWebCardAndFirmware() = runBlocking {
        val app = connectedApp()
        val account = app.store.session()
        val client = InventoryClient { app.api.request(it, session = account) }
        val numeric = client.page(InventoryClient.query("11", "R2"))
        assertTrue("R2 0011 must exist in the authorized server", numeric.items.isNotEmpty())
        val card = numeric.items.first { it.getString("nombre").endsWith("-0011") }
        val fullName = card.getString("nombre")
        // Synthetic camera frame; this does not claim a physical R2 or physical QR was scanned.
        val matrix = QRCodeWriter().encode(fullName, BarcodeFormat.QR_CODE, 320, 320)
        val pixels = IntArray(320 * 320) { if (matrix[it % 320, it / 320]) android.graphics.Color.BLACK else android.graphics.Color.WHITE }
        val decoded = MultiFormatReader().decode(BinaryBitmap(HybridBinarizer(RGBLuminanceSource(320, 320, pixels)))).text
        val scanned = client.page(InventoryClient.query(decoded, scanned = true))
        assertEquals(card.getInt("pcb_id"), scanned.items.single().getInt("pcb_id"))
        val detail = client.detail(card.getInt("pcb_id"))
        assertEquals(InventoryClient.text(card, "firmware"), InventoryClient.text(detail, "firmware"))
        assertTrue("Programming state must come from the same web service", detail.has("programming"))
        assertTrue(app.store.matches(account))
        println("TQT_READ_ONLY numeric-and-decoded-QR match; detail and web programming state match; session preserved")
    }
    @Test fun allTypesPaginationDoesNotStopAtOneHundred() = runBlocking {
        val app = connectedApp()
        val account = app.store.session()
        val client = InventoryClient { app.api.request(it, session = account) }
        var offset = 0
        val ids = mutableSetOf<Int>()
        val types = mutableSetOf<String>()
        var total: Int
        do {
            val page = client.page(InventoryQuery(""), offset)
            total = page.total
            assertTrue(page.items.isNotEmpty() || offset == total)
            page.items.forEach { assertTrue("Repeated PCB across pages", ids.add(it.getInt("pcb_id"))); types += it.getString("tipo") }
            assertTrue(page.nextOffset > offset || offset == total)
            offset = page.nextOffset
        } while (offset < total)
        assertEquals(total, ids.size)
        assertTrue(types.containsAll(listOf("R1", "R2", "R3")))
        assertTrue(app.store.matches(account))
        println("TQT_READ_ONLY paged inventory complete total=$total; R1/R2/R3 present; session preserved")
    }
    @Test fun managerRecoversFromEmptySearchWithoutNotFoundDialog() = runBlocking {
        val app = connectedApp()
        val account = app.store.session()
        val manager = UpdateManager(app, app.store, app.api)
        manager.refresh("9999", "R2")
        val empty = withTimeout(30000) { manager.state.first { it.inventoryLoaded && !it.busy && it.inventoryQuery == "9999" } }
        assertNull(empty.error); assertNull(empty.inventoryError)
        assertEquals(0, empty.inventoryTotal)
        manager.refresh("11", "R2")
        val found = withTimeout(30000) { manager.state.first { it.inventoryLoaded && !it.busy && it.inventoryQuery == "0011" } }
        assertEquals(1, found.devices.size)
        assertNull(found.error); assertNull(found.inventoryError)
        manager.select(found.devices.single())
        val selected = withTimeout(30000) { manager.state.first { it.selected != null && !it.busy } }
        assertNull(selected.catalogueError)
        assertTrue(selected.selected!!.has("programming"))
        assertTrue(app.store.matches(account))
        println("TQT_READ_ONLY manager empty search recovered to 0011; no dialog errors; detail and catalogue loaded")
    }
}
