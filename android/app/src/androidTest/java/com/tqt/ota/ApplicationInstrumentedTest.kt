package com.tqt.ota

import android.os.Build
import android.util.Base64
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.tqt.ota.offline.OfflineKeys
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayInputStream
import java.security.KeyStore
import java.security.cert.CertificateFactory
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import kotlinx.coroutines.test.StandardTestDispatcher

/** Explicit emulator-only integration fixture; production TLS validation is never relaxed. */
@RunWith(AndroidJUnit4::class)
@OptIn(ExperimentalTestApi::class)
class ApplicationInstrumentedTest {
    // Queue frames explicitly: an unconfined test dispatcher can resume composition on the HTTP producer thread.
    @get:Rule val compose = createEmptyComposeRule(effectContext = StandardTestDispatcher())

    @Test fun keystoreIdentityIsStableAndPublicOnly() {
        val first = OfflineKeys().publicKeyHex()
        assertEquals(130, first.length)
        assertTrue(first.startsWith("04"))
        assertEquals(first, OfflineKeys().publicKeyHex())
    }

    @Test fun realHttpsLoginInventoryAndNavigation() {
        val args = InstrumentationRegistry.getArguments()
        org.junit.Assume.assumeTrue("Requires the explicitly configured local emulator fixture", args.containsKey("fixtureCertificate"))
        require(Build.HARDWARE in listOf("ranchu", "goldfish") && Build.PRODUCT.startsWith("sdk_")) { "Emulator only" }
        val origin = "https://10.0.2.2:18143"
        val certificate = CertificateFactory.getInstance("X.509").generateCertificate(ByteArrayInputStream(Base64.decode(args.getString("fixtureCertificate"), Base64.NO_WRAP)))
        val trust = KeyStore.getInstance(KeyStore.getDefaultType()).apply { load(null); setCertificateEntry("exclusive-local-fixture", certificate) }
        val managers = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm()).apply { init(trust) }
        val ssl = SSLContext.getInstance("TLS").apply { init(null, managers.trustManagers, null) }
        val previous = HttpsURLConnection.getDefaultSSLSocketFactory()
        val app = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as TqtApplication
        app.store.logout(); app.store.baseUrl = origin
        app.updates = UpdateManager(app, app.store, app.api)
        HttpsURLConnection.setDefaultSSLSocketFactory(ssl.socketFactory)
        try {
            ActivityScenario.launch(MainActivity::class.java).use {
                compose.waitUntil(10000) { compose.onAllNodesWithText("Correo de Inventario TQT").fetchSemanticsNodes().isNotEmpty() }
                compose.onNodeWithText("Correo de Inventario TQT").performTextInput("android.qa@example.invalid")
                compose.onNode(hasSetTextAction() and hasText("Contraseña")).performTextInput("Prueba-OTA-2026!")
                compose.onNodeWithText("Iniciar sesión").performScrollTo().performClick()
                compose.waitUntil(30000) { compose.onAllNodesWithText("Firmware, al día.").fetchSemanticsNodes().isNotEmpty() }
                compose.onNodeWithText("android.qa@example.invalid").assertIsDisplayed()
                compose.waitUntil(30000) { compose.onAllNodesWithText("Seleccionar tarjeta").fetchSemanticsNodes().isNotEmpty() }
                compose.onNodeWithText("Historial").performClick()
                compose.onNodeWithText("Sincronizar resultados pendientes").assertIsDisplayed().performClick()
                compose.onNodeWithText("Bluetooth", useUnmergedTree = true).performClick()
                compose.onNodeWithText("Selecciona una R2 en Tarjetas").assertIsDisplayed()
                compose.onNode(hasScrollToIndexAction()).performScrollToNode(hasText("Revisar y actualizar"))
                compose.onNodeWithText("Revisar y actualizar").assertIsNotEnabled()
                java.io.File(app.cacheDir, "tqt-ui.png").outputStream().use { output ->
                    compose.onRoot().captureToImage().asAndroidBitmap().compress(android.graphics.Bitmap.CompressFormat.PNG, 100, output)
                }
            }
        } finally { app.store.logout(); HttpsURLConnection.setDefaultSSLSocketFactory(previous) }
    }
}
