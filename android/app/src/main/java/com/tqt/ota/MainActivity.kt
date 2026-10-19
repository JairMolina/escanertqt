package com.tqt.ota

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.tqt.ota.ble.NearbyDevice
import com.tqt.ota.data.InventoryClient
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import org.json.JSONObject

private val Gold = Color(0xFFD9A441)
private val Navy = Color(0xFF0A1020)
private val Panel = Color(0xFF121B33)
private val Ink = Color(0xFFE9EEF5)
private val Muted = Color(0xFFB0BDD5)
private val Good = Color(0xFF3FD08A)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val application = application as TqtApplication
        application.updates.restore()
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = Gold, onPrimary = Navy, background = Navy,
                surface = Panel, onSurface = Ink, secondary = Color(0xFFB08CFF), outline = Color(0xFF485575))) {
                TqtScreen(application)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun TqtScreen(app: TqtApplication) {
    val manager = app.updates
    val state by manager.state.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var server by remember { mutableStateOf(app.store.baseUrl) }
    var email by remember { mutableStateOf(app.store.email) }
    var password by remember { mutableStateOf("") }
    var query by rememberSaveable { mutableStateOf("") }
    var firmware by remember { mutableStateOf<JSONObject?>(null) }
    var radio by remember { mutableStateOf<NearbyDevice?>(null) }
    var confirm by remember { mutableStateOf(false) }
    var permissionError by remember { mutableStateOf(false) }
    val activity = androidx.activity.compose.LocalActivity.current ?: return
    val required = if (Build.VERSION.SDK_INT >= 31) arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        else arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
    val permissions = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
        if (required.all { result[it] == true || activity.checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }) manager.scan()
        else permissionError = true
    }
    val notificationPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    var qrError by remember { mutableStateOf<String?>(null) }
    val qrScanner = rememberLauncherForActivityResult(ScanContract()) { result ->
        result.contents?.let { code ->
            try {
                val normalized = InventoryClient.query(code, scanned = true)
                query = normalized.text; tab = 0
                manager.refresh(normalized.text, normalized.type, scanned = true)
            } catch (error: IllegalArgumentException) { qrError = error.message }
        }
    }
    fun scan() {
        if (required.all { activity.checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }) manager.scan()
        else permissions.launch(required)
    }
    LaunchedEffect(state.email) { if (state.email.isNotEmpty()) password = "" }
    LaunchedEffect(state.selected?.optInt("pcb_id")) { radio = null; firmware = null }
    LaunchedEffect(state.firmwares) { firmware = state.firmwares.firstOrNull() }
    LaunchedEffect(state.inventoryQuery) { query = state.inventoryQuery }
    Scaffold(modifier = Modifier.navigationBarsPadding().imePadding(), containerColor = Navy, topBar = {
        TopAppBar(title = { Row(verticalAlignment = Alignment.CenterVertically) {
            Text("TQT", color = Gold, fontWeight = FontWeight.Black, letterSpacing = 3.sp)
            Spacer(Modifier.width(12.dp)); Text("Actualización de tarjetas", fontSize = 15.sp)
        } }, actions = {
            if (state.email.isNotEmpty()) TextButton(onClick = { manager.logout() }, enabled = !state.updating && !state.busy) { Text("Salir") }
        }, colors = TopAppBarDefaults.topAppBarColors(containerColor = Navy))
    }, bottomBar = {
        if (state.email.isNotEmpty()) NavigationBar(containerColor = Panel) {
            listOf("Tarjetas", "Detalle", "Historial").forEachIndexed { index, label ->
                NavigationBarItem(selected = tab == index, onClick = { tab = index }, icon = { Text(listOf("PCB", "INFO", "LOG")[index], fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold) }, label = { Text(label) })
            }
        }
    }) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            if (state.email.isEmpty()) {
                item {
                    Spacer(Modifier.height(24.dp))
                    Text("Tu inventario.\nMás cerca.", fontSize = 36.sp, lineHeight = 40.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(12.dp))
                    Text("Firmware autorizado, Bluetooth y trazabilidad en un solo lugar.", color = Muted)
                }
                item { Section("ACCESO PRIVADO") {
                    OutlinedTextField(email, { email = it }, label = { Text("Correo de Inventario TQT") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email), singleLine = true, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(password, { password = it }, label = { Text("Contraseña") }, visualTransformation = PasswordVisualTransformation(), singleLine = true, modifier = Modifier.fillMaxWidth())
                    Button(onClick = { manager.login(server, email, password) }, enabled = email.isNotBlank() && password.isNotEmpty() && !state.busy, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text(if (state.busy) "Conectando…" else "Iniciar sesión") }
                    OutlinedTextField(server, { server = it }, label = { Text("Servidor HTTPS") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Text("Usa tu cuenta habitual. La aplicación no contiene contraseñas compartidas.", color = Muted, style = MaterialTheme.typography.bodySmall)
                } }
            } else {
                item {
                    Text(when (tab) { 0 -> "Tu inventario TQT."; 1 -> "Detalle de tarjeta."; else -> "Cada cambio cuenta." }, fontSize = 30.sp, fontWeight = FontWeight.Bold)
                    Text(state.email, color = Muted, style = MaterialTheme.typography.bodySmall)
                }
                if ((state.release?.optInt("version_code") ?: 0) > BuildConfig.VERSION_CODE) item { Section("NUEVA VERSIÓN DE LA APLICACIÓN") {
                    Text("TQT ${state.release?.optString("version_name")} está disponible.")
                    OutlinedButton(onClick = { activity.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(app.store.baseUrl + "/android"))) }) { Text("Abrir descarga privada en Inventario TQT") }
                    Text("Inicia sesión en el navegador para descargar. Android comprueba que la firma conserve la identidad de la aplicación.", color = Muted)
                } }
                if (state.updating || state.total > 0) item { Section("OPERACIÓN EN CURSO") {
                    Text(state.stage, fontWeight = FontWeight.Bold)
                    if (state.total > 0) {
                        LinearProgressIndicator(progress = { (state.confirmed.toFloat() / state.total).coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth(), color = Gold)
                        Text("${state.confirmed / 1024} / ${state.total / 1024} KiB confirmados por la tarjeta", color = Muted)
                    }
                    Text("Mantén la tarjeta encendida y el teléfono cerca hasta verificar el nuevo arranque.", color = Muted)
                    if (state.updating) OutlinedButton(onClick = { manager.cancel() }) { Text("Interrumpir y dejar pendiente de verificación") }
                } }
                if (tab == 0) {
                    if (state.packages.isNotEmpty()) item { Section("PAQUETES OFFLINE EN ESTE TELÉFONO") {
                        Text("Cada permiso corresponde a una tarjeta, una imagen y este teléfono. Requiere FW 4.3 ya instalado y vinculado online.", color = Muted)
                        state.packages.forEach { pkg -> OutlinedButton(onClick = { manager.selectOffline(pkg); tab = 1 }, enabled = !state.busy && !state.updating) {
                            Text("${pkg.optString("nombre")} · FW ${pkg.optString("fw")}")
                        } }
                    } }
                    item { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(query, { query = it }, label = { Text("Número, nombre o MAC") }, singleLine = true,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                            keyboardActions = KeyboardActions(onSearch = { manager.refresh(query) }),
                            enabled = !state.busy && !state.updating, modifier = Modifier.fillMaxWidth().testTag("inventoryQuery"))
                        Text("Ejemplo: 11 encuentra la serie 0011. También puedes escanear su QR.", color = Muted, style = MaterialTheme.typography.bodySmall)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = { manager.refresh(query) }, enabled = !state.busy && !state.updating, modifier = Modifier.weight(1f).heightIn(min = 48.dp)) { Text("Buscar") }
                            OutlinedButton(onClick = { qrScanner.launch(ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                                .setPrompt("Escanea el QR de una tarjeta TQT").setBeepEnabled(false).setOrientationLocked(false).setCaptureActivity(QrCaptureActivity::class.java)) },
                                enabled = !state.busy && !state.updating, modifier = Modifier.weight(1f).heightIn(min = 48.dp)) { Text("Escanear QR") }
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            listOf("", "R1", "R2", "R3").forEach { type -> FilterChip(selected = state.inventoryType == type,
                                onClick = { manager.refresh(query, type) }, enabled = !state.busy && !state.updating,
                                label = { Text(type.ifEmpty { "Todas" }) }) }
                        }
                    } }
                    if (state.inventoryError != null) item { Section("NO SE PUDO COMPLETAR LA CONSULTA") {
                        Text(state.inventoryError!!)
                        if (state.inventoryLoaded) Text("Los datos anteriores permanecen visibles; actualiza la consulta antes de usarlos.", color = Muted)
                        OutlinedButton(onClick = { manager.refresh(query) }, enabled = !state.busy) { Text("Reintentar consulta") }
                    } }
                    if (state.inventoryLoaded) item { Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("${state.devices.size} de ${state.inventoryTotal} tarjetas", color = Muted)
                        TextButton(onClick = { query = ""; manager.refresh("", "") }, enabled = !state.busy && !state.updating) { Text("Ver todas") }
                    } }
                    if (state.devices.isEmpty() && state.inventoryLoaded && !state.busy && state.inventoryError == null) item {
                        Text("No se encontraron tarjetas. Revisa el número, cambia el tipo o pulsa Ver todas.", color = Muted)
                    }
                    items(state.devices, key = { it.getInt("pcb_id") }) { device ->
                        OutlinedCard(onClick = { manager.select(device); tab = 1 }, enabled = !state.updating, modifier = Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text("${device.optString("tipo")} · HW ${device.optString("hw")}", color = Color(0xFFB08CFF), style = MaterialTheme.typography.labelLarge)
                                Text(device.optString("nombre"), fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                                Text(InventoryClient.status(device), color = if (device.optJSONObject("programming")?.optBoolean("verified") == true) Good else Gold)
                                Text("FW ${InventoryClient.text(device, "firmware").ifEmpty { "sin registrar" }} · ${device.optString("estado_ciclo")}", color = Muted)
                                Text("Ver detalle", color = Gold)
                            }
                        }
                    }
                    if (state.inventoryOffset < state.inventoryTotal) item { OutlinedButton(onClick = { manager.loadMore() }, enabled = !state.busy && !state.updating, modifier = Modifier.fillMaxWidth()) { Text("Cargar más tarjetas") } }
                }
                if (tab == 1) {
                    item { Section("TARJETA SELECCIONADA") {
                        Text(state.selected?.optString("nombre") ?: "Selecciona una tarjeta en Tarjetas", fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold)
                        if (state.selected != null) {
                            val pcb = state.selected!!
                            Text(InventoryClient.status(pcb), color = if (pcb.optJSONObject("programming")?.optBoolean("verified") == true) Good else Gold, fontWeight = FontWeight.Bold)
                            Text("Firmware registrado: ${InventoryClient.text(pcb, "firmware").ifEmpty { "sin registrar" }}")
                            Text("Hardware: ${pcb.optString("hw")} · Estado: ${pcb.optString("estado_ciclo")}", color = Muted)
                            Text("MAC: ${InventoryClient.text(pcb, "mac").ifEmpty { "sin registrar" }}", fontFamily = FontFamily.Monospace, color = Muted)
                            Text("Tarjeta asociada: ${InventoryClient.text(pcb, "id_tarjeta_num").ifEmpty { "sin asignar" }}", color = Muted)
                            val programming = pcb.optJSONObject("programming")
                            if (programming != null) {
                                Text(if (programming.optBoolean("verified")) "Programación verificada en la web." else "La web no registra una programación verificada para los datos actuales.", color = Muted)
                                InventoryClient.text(programming, "latest_fw").takeIf { it.isNotEmpty() }?.let { Text("Último firmware compatible: $it", color = Muted) }
                                InventoryClient.text(programming, "error").takeIf { it.isNotEmpty() }?.let { Text(it, color = Muted) }
                            }
                            if (!state.androidProgramming) Text("Puedes consultar el inventario. La programación Android aún no está habilitada en este servidor.", color = Muted)
                            if (state.catalogueError != null) Text(state.catalogueError!!, color = Gold)
                        }
                        if (state.selected?.optString("tipo") == "R2" || state.offlineSelected != null) {
                            Text("Firmware de destino", style = MaterialTheme.typography.labelLarge)
                            state.firmwares.forEach { image -> Row(verticalAlignment = Alignment.CenterVertically) {
                                RadioButton(selected = firmware?.optString("id") == image.optString("id"), onClick = { firmware = image }, enabled = !state.updating)
                                Text("FW ${image.optString("fw")} · HW ${image.optString("hw")}")
                            } }
                            if (state.firmwares.isEmpty()) Text("No hay una imagen OTA compatible disponible.", color = Muted)
                        }
                        Button(onClick = { scan() }, enabled = (state.selected?.optString("tipo") == "R2" || state.offlineSelected != null) && !state.busy && !state.updating, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text(if (state.busy) "Buscando…" else "Buscar por Bluetooth") }
                        Text(if (state.offlineSelected != null) "Paquete offline seleccionado: se verifican firma, teléfono, tarjeta y contador antes del envío." else "4.2 y el alta genérica 4.0 requieren Internet. En 4.3 puedes autorizar previamente un paquete para usarlo sin conexión.", color = Muted, style = MaterialTheme.typography.bodySmall)
                    } }
                    items(state.nearby, key = { it.address }) { candidate ->
                        OutlinedCard(onClick = { radio = candidate }, enabled = !state.updating, modifier = Modifier.fillMaxWidth()) {
                            Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                                RadioButton(selected = radio?.address == candidate.address, onClick = { radio = candidate })
                                Column { Text(candidate.name.ifEmpty { "Dispositivo TQT" }, fontWeight = FontWeight.Bold); Text("${candidate.address} · ${candidate.rssi} dBm", fontFamily = FontFamily.Monospace, color = Muted) }
                            }
                        }
                    }
                    item { Button(onClick = { confirm = true }, enabled = (state.androidProgramming || state.offlineSelected != null) && state.selected != null && firmware != null && radio != null && !state.updating && !state.busy && state.role != "consultor", modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text("Revisar y actualizar") } }
                    if (state.offlineSelected == null) item { OutlinedButton(onClick = { manager.prepareOffline(state.selected!!, firmware!!, radio!!) }, enabled = state.androidProgramming && state.selected?.optString("tipo") == "R2" && firmware != null && radio != null && !state.updating && !state.busy && state.role != "consultor", modifier = Modifier.fillMaxWidth()) { Text("Autorizar y guardar paquete offline") } }
                }
                if (tab == 2) {
                    item { OutlinedButton(onClick = { manager.synchronizeNow() }, enabled = !state.updating) { Text("Sincronizar resultados pendientes") } }
                    if (state.history.isEmpty()) item { Text("Las actualizaciones de este teléfono aparecerán aquí. Los registros centrales se conservan en Inventario TQT.", color = Muted) }
                    items(state.history, key = { it.getString("id") }) { record -> Section(record.optString("nombre")) {
                        val status = record.optString("state")
                        Text(stateLabel(status), color = if (status == "verified") Good else Gold, fontWeight = FontWeight.Bold)
                        Text(record.optString("id"), fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall, color = Muted)
                        if (record.has("error")) Text(record.optString("error"), color = Muted)
                        if (status in listOf("pending_verification", "preparation_uncertain")) OutlinedButton(onClick = { manager.verify(record) }, enabled = !state.busy && !state.updating) { Text("Verificar dispositivo sin reinstalar") }
                        if (status == "migration_required") Text("La identidad requiere una segunda sesión de actualización. Selecciona la misma tarjeta y firmware.", color = Muted)
                    } }
                }
                if (state.busy) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
                item { Text("TQT ${BuildConfig.VERSION_NAME} · Distribución privada\nInventario conectado · Programación R2 ESP32", color = Muted, style = MaterialTheme.typography.bodySmall) }
            }
        }
    }
    if (confirm) AlertDialog(onDismissRequest = { confirm = false }, title = { Text("Confirmar tarjeta y firmware") }, text = {
        Text("${state.selected?.optString("nombre")}\n${radio?.name} · ${radio?.address}\nDestino FW ${firmware?.optString("fw")}\n\nComprueba físicamente la unidad. La transferencia no se marcará exitosa hasta verificar el nuevo arranque.")
    }, confirmButton = { Button(onClick = {
        confirm = false
        if (Build.VERSION.SDK_INT >= 33 && activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        val offline = state.offlineSelected
        if (offline != null) manager.startOffline(offline, radio!!) else manager.start(state.selected!!, firmware!!, radio!!)
    }) { Text("Autorizar actualización") } }, dismissButton = { TextButton(onClick = { confirm = false }) { Text("Volver") } })
    val error = state.error ?: if (permissionError) "Permite Bluetooth cercano (o ubicación en Android 8–11) en Ajustes para buscar tarjetas." else null
    if (error != null) AlertDialog(onDismissRequest = { manager.dismissError(); permissionError = false }, title = { Text("Revisar operación") }, text = { Text(error) }, confirmButton = { TextButton(onClick = { manager.dismissError(); permissionError = false }) { Text("Entendido") } })
    if (qrError != null) AlertDialog(onDismissRequest = { qrError = null }, title = { Text("Revisar código QR") }, text = { Text(qrError!!) }, confirmButton = { TextButton(onClick = { qrError = null }) { Text("Entendido") } })
}

@Composable private fun Section(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Panel)) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(title, color = Gold, fontSize = 12.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
            content()
        }
    }
}
private fun stateLabel(value: String): String = when (value) {
    "verified" -> "Verificada y sincronizada"
    "pending_sync" -> "Arranque observado · pendiente de validación del servidor"
    "pending_failure_sync" -> "Interrumpida · registro pendiente de sincronizar"
    "pending_verification" -> "Pendiente de verificar el nuevo arranque"
    "preparing", "preparation_uncertain" -> "Autorización pendiente de recuperar"
    "conflict" -> "Conflicto: requiere revisión"
    "accepted_history" -> "Evidencia histórica recibida; estado actual sin modificar"
    "migration_required" -> "Primera transición de identidad completada"
    "failed" -> "Fallida"
    "cancelled" -> "Cancelada"
    else -> value
}
