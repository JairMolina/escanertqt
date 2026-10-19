package com.tqt.ota.data

import org.json.JSONObject
import java.net.URLEncoder

data class InventoryQuery(val text: String, val type: String = "")
data class InventoryPage(val items: List<JSONObject>, val total: Int, val nextOffset: Int)

/** Uses the same authenticated, read-only inventory API as the web, including older servers. */
class InventoryClient(private val get: suspend (String) -> JSONObject) {
    companion object {
        fun text(value: JSONObject, key: String): String = if (value.isNull(key)) "" else value.optString(key).trim()
        private val name = Regex("TQT[-_\\s]+(R[123])[-_\\s]+V(\\d{1,3})[-_\\s]+(\\d{1,4})(?!\\d)", RegexOption.IGNORE_CASE)
        fun query(input: String, type: String = "", scanned: Boolean = false): InventoryQuery {
            val raw = input.trim()
            require(raw.length <= 2000) { "El código es demasiado largo. Usa la etiqueta de una tarjeta TQT." }
            require(type in listOf("", "R1", "R2", "R3"))
            val names = name.findAll(raw).toList()
            if (names.isNotEmpty()) {
                // A paired DYMO label contains R1, MAC1, R2, MAC2. Prefer its R2.
                val match = names.firstOrNull { it.groupValues[1].equals("R2", true) } ?: names.first()
                val kind = match.groupValues[1].uppercase()
                val hw = match.groupValues[2].toInt()
                val serial = match.groupValues[3].toInt()
                require(hw > 0 && serial > 0) { "La versión y el número de tarjeta deben ser mayores que cero." }
                return InventoryQuery("TQT-$kind-V$hw-${serial.toString().padStart(4, '0')}", kind)
            }
            val short = Regex("^(R[123])[-_\\s]+(\\d{1,4})$", RegexOption.IGNORE_CASE).matchEntire(raw)
            val number = short?.groupValues?.get(2) ?: raw
            if (number.matches(Regex("\\d{1,4}"))) {
                require(number.toInt() > 0) { "El número de tarjeta debe ser mayor que cero." }
                return InventoryQuery(number.padStart(4, '0'), short?.groupValues?.get(1)?.uppercase() ?: type)
            }
            val mac = raw.replace(Regex("[:-]"), "")
            if (mac.matches(Regex("[a-fA-F0-9]{12}"))) return InventoryQuery(mac.chunked(2).joinToString(":"), type)
            require(!scanned && raw.length <= 60 && !raw.contains('\n')) { "El QR no contiene una tarjeta TQT ni una MAC válida. Puedes buscar por número." }
            return InventoryQuery(raw, type)
        }
        fun normalize(pcb: JSONObject): JSONObject = JSONObject(pcb.toString()).apply {
            put("pcb_id", pcb.getInt("id")); put("hw", text(pcb, "version"))
        }
        fun status(pcb: JSONObject): String {
            val state = pcb.optJSONObject("programming")
            return when (state?.optString("state")) {
                "updated" -> "Programada · actualizada"
                "outdated" -> "Programada · actualización disponible"
                "unprogrammed" -> if (text(pcb, "firmware").isEmpty()) "Sin programar" else "Firmware registrado · sin verificar"
                "error" -> "Error de programación o verificación"
                "busy" -> "Programación o verificación en curso"
                else -> if (text(pcb, "firmware").isEmpty()) "Sin programación registrada" else "Firmware registrado · sin verificar"
            }
        }
        private fun objects(value: JSONObject): List<JSONObject> {
            val items = value.getJSONArray("items")
            return (0 until items.length()).map { items.getJSONObject(it) }
        }
    }
    private fun encoded(value: String) = URLEncoder.encode(value, "UTF-8")
    suspend fun page(query: InventoryQuery, offset: Int = 0): InventoryPage {
        val result = get("/api/pcb?limit=100&offset=$offset&q=${encoded(query.text)}&tipo=${encoded(query.type)}")
        val items = objects(result).map(::normalize)
        if (items.any { text(it, "tipo") == "R2" }) {
            try {
                val states = objects(get("/api/esp32/r2/status")).associateBy { it.getInt("pcb_id") }
                items.forEach { pcb -> states[pcb.getInt("pcb_id")]?.let { pcb.put("programming", it) } }
            } catch (error: ApiFailure) { if (error.status !in listOf(404, 503)) throw error }
        }
        return InventoryPage(items, result.getInt("total"), offset + items.size)
    }
    suspend fun detail(id: Int): JSONObject {
        val pcb = normalize(get("/api/pcb/$id"))
        if (text(pcb, "tipo") == "R2") {
            try {
                val states = objects(get("/api/esp32/r2/status"))
                states.firstOrNull { it.optInt("pcb_id") == id }?.let { pcb.put("programming", it) }
            } catch (error: ApiFailure) {
                if (error.status !in listOf(404, 503)) throw error
                pcb.put("status_notice", "El servidor no ofrece la verificación de programación. Se muestran los datos del inventario.")
            }
        }
        return pcb
    }
    suspend fun androidProgrammingAvailable(): Boolean = try {
        get("/api/android/devices?limit=1"); true
    } catch (error: ApiFailure) {
        if (error.status == 404) false else throw error
    }
    suspend fun firmwares(hw: String): List<JSONObject> = objects(get("/api/esp32/firmwares?hw=${encoded(hw)}"))
}
