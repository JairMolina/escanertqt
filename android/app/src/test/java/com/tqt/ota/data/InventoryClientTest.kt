package com.tqt.ota.data

import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class InventoryClientTest {
    @Test fun shortNumbersResolveToPaddedSerialWithoutAssumingHardware() {
        for (value in listOf("11", "0011", " 11 ")) assertEquals(InventoryQuery("0011", "R2"), InventoryClient.query(value, "R2"))
        assertEquals(InventoryQuery("0011", "R2"), InventoryClient.query("r2 11"))
        assertEquals(InventoryQuery("0011"), InventoryClient.query("11"))
    }
    @Test fun qrNamesAndPairedDymoLabelsResolveToTheirR2() {
        assertEquals(InventoryQuery("TQT-R2-V30-0011", "R2"), InventoryClient.query("tqt_r2_v030_11", scanned = true))
        val label = "TQT-R1-V30-0021\naa:bb:cc:dd:ee:01\nTQT-R2-V31-0011\naa:bb:cc:dd:ee:02"
        assertEquals(InventoryQuery("TQT-R2-V31-0011", "R2"), InventoryClient.query(label, scanned = true))
        assertEquals("R3", InventoryClient.query("TQT-R3-V30-0007", scanned = true).type)
    }
    @Test fun macsAreAcceptedWithoutOpeningUrlsOrRunningQrContent() {
        assertEquals("aa:bb:cc:dd:ee:ff", InventoryClient.query("aabbccddeeff", scanned = true).text)
        assertEquals("AA:BB:CC:DD:EE:FF", InventoryClient.query("AA-BB-CC-DD-EE-FF", scanned = true).text)
        for (value in listOf("https://untrusted.invalid", "adb shell rm", "", "not a QR", "X".repeat(2001), "TQT-R2-V0-0011", "TQT-R2-V30-0000")) {
            assertThrows(value, IllegalArgumentException::class.java) { InventoryClient.query(value, scanned = true) }
        }
        assertThrows(IllegalArgumentException::class.java) { InventoryClient.query("0") }
    }
    @Test fun pageUsesWebContractAndPreservesPagingAndVerification() = runBlocking {
        val paths = mutableListOf<String>()
        val client = InventoryClient { path ->
            paths += path
            if (path.startsWith("/api/pcb?")) JSONObject("""{"total":151,"items":[{"id":9,"tipo":"R2","version":"30","nombre":"TQT-R2-V30-0011","firmware":"4.2"}]}""")
            else JSONObject("""{"items":[{"pcb_id":9,"state":"updated","verified":true}]}""")
        }
        val page = client.page(InventoryClient.query("11", "R2"), 100)
        assertEquals("/api/pcb?limit=100&offset=100&q=0011&tipo=R2", paths[0])
        assertEquals(151, page.total); assertEquals(101, page.nextOffset)
        assertEquals(9, page.items.single().getInt("pcb_id"))
        assertEquals("30", page.items.single().getString("hw"))
        assertEquals("Programada · actualizada", InventoryClient.status(page.items.single()))
    }
    @Test fun missingAndroidServiceDoesNotHideExistingInventory() = runBlocking {
        val client = InventoryClient { path ->
            if (path.startsWith("/api/android/")) throw ApiFailure(404, "Not Found")
            if (path.startsWith("/api/pcb?")) JSONObject("""{"total":1,"items":[{"id":1,"tipo":"R1","version":"30"}]}""")
            else error("Unexpected GET")
        }
        assertFalse(client.androidProgrammingAvailable())
        assertEquals(1, client.page(InventoryQuery("")).items.size)
    }
    @Test fun authorizationAndServerFailuresAreNeverTreatedAsMissingAndroidService() = runBlocking {
        for (status in listOf(401, 403, 500, 503)) {
            val client = InventoryClient { throw ApiFailure(status, "failure") }
            try { client.androidProgrammingAvailable(); fail("Expected $status") }
            catch (error: ApiFailure) { assertEquals(status, error.status) }
        }
    }
    @Test fun missingVerificationDoesNotInventProgrammingEvidenceOrNullText() = runBlocking {
        val client = InventoryClient { path ->
            if (path.startsWith("/api/pcb/")) JSONObject("""{"id":11,"tipo":"R2","version":"30","firmware":null,"mac":null} """)
            else throw ApiFailure(404, "Not Found")
        }
        val pcb = client.detail(11)
        assertEquals("", InventoryClient.text(pcb, "firmware"))
        assertEquals("Sin programación registrada", InventoryClient.status(pcb))
        assertFalse(pcb.has("programming"))
        pcb.put("firmware", "4.2")
        assertEquals("Firmware registrado · sin verificar", InventoryClient.status(pcb))
    }
    @Test fun currentFirmwareIsDistinctFromLastProgrammingError() {
        val pcb = JSONObject("""{"firmware":"4.2","programming":{"state":"error","verified":false}}""")
        assertEquals("Error de programación o verificación", InventoryClient.status(pcb))
        assertEquals("4.2", InventoryClient.text(pcb, "firmware"))
    }
}
