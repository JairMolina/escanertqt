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
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.tqt.ota.ble.NearbyDevice
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
    var tab by remember { mutableIntStateOf(0) }
    var server by remember { mutableStateOf(app.store.baseUrl) }
    var email by remember { mutableStateOf(app.store.email) }
    var password by remember { mutableStateOf("") }
    var query by remember { mutableStateOf("") }
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
    fun scan() {
        if (required.all { activity.checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }) manager.scan()
        else permissions.launch(required)
    }
    LaunchedEffect(state.email) { if (state.email.isNotEmpty()) password = "" }
    LaunchedEffect(state.selected?.optInt("pcb_id")) { radio = null; firmware = null }
    LaunchedEffect(state.firmwares) { firmware = state.firmwares.firstOrNull() }
    Scaffold(containerColor = Navy, topBar = {
        TopAppBar(title = { Row(verticalAlignment = Alignment.CenterVertically) {
            Text("TQT", color = Gold, fontWeight = FontWeight.Black, letterSpacing = 3.sp)
            Spacer(Modifier.width(12.dp)); Text("Actualización de tarjetas", fontSize = 15.sp)
        } }, actions = {
            if (state.email.isNotEmpty()) TextButton(onClick = { manager.logout() }, enabled = !state.updating && !state.busy) { Text("Salir") }
        }, colors = TopAppBarDefaults.topAppBarColors(containerColor = Navy))
    }, bottomBar = {
        if (state.email.isNotEmpty()) NavigationBar(containerColor = Panel) {
            listOf("Tarjetas", "Bluetooth", "Historial").forEachIndexed { index, label ->
                NavigationBarItem(selected = tab == index, onClick = { tab = index }, icon = { Text(listOf("R2", "BLE", "LOG")[index], fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold) }, label = { Text(label) })
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
                    Text(when (tab) { 0 -> "Firmware, al día."; 1 -> "Una conexión segura."; else -> "Cada cambio cuenta." }, fontSize = 30.sp, fontWeight = FontWeight.Bold)
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
                    item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        OutlinedTextField(query, { query = it }, label = { Text("Buscar tarjeta, serie o MAC") }, singleLine = true, modifier = Modifier.weight(1f))
                        Button(onClick = { manager.refresh(query) }, enabled = !state.busy && !state.updating) { Text("Buscar") }
                    } }
                    if (state.devices.isEmpty() && !state.busy) item { Text("No hay R2 para mostrar. Consulta el servidor o ajusta tu búsqueda.", color = Muted) }
                    items(state.devices, key = { it.getInt("pcb_id") }) { device ->
                        OutlinedCard(onClick = { manager.select(device); tab = 1 }, enabled = !state.updating, modifier = Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text("R2 · HW ${device.optString("hw")}", color = Color(0xFFB08CFF), style = MaterialTheme.typography.labelLarge)
                                Text(device.optString("nombre"), fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                                Text("Firmware ${device.optString("firmware").ifEmpty { "sin confirmar" }}  ·  ${device.optString("mac").ifEmpty { "Identidad por verificar" }}", color = Muted)
                                Text("Seleccionar tarjeta", color = Gold)
                            }
                        }
                    }
                }
                if (tab == 1) {
                    item { Section("TARJETA SELECCIONADA") {
                        Text(state.selected?.optString("nombre") ?: "Selecciona una R2 en Tarjetas", fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold)
                        Text("El nombre del anuncio solo ayuda a localizarla. El servidor comprueba identidad y compatibilidad antes de autorizar.", color = Muted)
                        if (state.selected != null) {
                            Text("Firmware de destino", style = MaterialTheme.typography.labelLarge)
                            state.firmwares.forEach { image -> Row(verticalAlignment = Alignment.CenterVertically) {
                                RadioButton(selected = firmware?.optString("id") == image.optString("id"), onClick = { firmware = image }, enabled = !state.updating)
                                Text("FW ${image.optString("fw")} · HW ${image.optString("hw")}")
                            } }
                            if (state.firmwares.isEmpty()) Text("No hay una imagen OTA compatible disponible.", color = Muted)
                        }
                        Button(onClick = { scan() }, enabled = state.selected != null && !state.busy && !state.updating, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text(if (state.busy) "Buscando…" else "Buscar por Bluetooth") }
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
                    item { Button(onClick = { confirm = true }, enabled = state.selected != null && firmware != null && radio != null && !state.updating && !state.busy && state.role != "consultor", modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text("Revisar y actualizar") } }
                    if (state.offlineSelected == null) item { OutlinedButton(onClick = { manager.prepareOffline(state.selected!!, firmware!!, radio!!) }, enabled = state.selected != null && firmware != null && radio != null && !state.updating && !state.busy && state.role != "consultor", modifier = Modifier.fillMaxWidth()) { Text("Autorizar y guardar paquete offline") } }
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
                item { Text("TQT 0.1.0 · Distribución privada\nR2 ESP32 · Inventario y permisos centrales", color = Muted, style = MaterialTheme.typography.bodySmall) }
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
