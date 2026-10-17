package com.tqt.ota.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.io.ByteArrayOutputStream

class ApiFailure(val status: Int, message: String) : IOException(message)

class TqtApi(private val store: PrivateStore) {
    private val loginLock = Mutex()
    companion object {
        fun validatedOrigin(input: String): String {
            val uri = URI(input.trim().trimEnd('/'))
            require(uri.scheme == "https" && !uri.host.isNullOrBlank() && uri.userInfo == null && uri.query == null && uri.fragment == null && uri.path.orEmpty().isEmpty()) {
                "Usa el origen HTTPS del servidor, sin usuario ni rutas."
            }
            return uri.toASCIIString()
        }
    }
    suspend fun request(path: String, body: JSONObject? = null, method: String = if (body == null) "GET" else "POST",
                        session: SessionContext = store.session()): JSONObject = withContext(Dispatchers.IO) {
        require(path.startsWith("/api/") && !path.contains("\\"))
        if (!store.matches(session)) throw SessionChangedException()
        val origin = validatedOrigin(session.origin)
        val connection = URI(origin + path).toURL().openConnection() as HttpURLConnection
        try {
            connection.instanceFollowRedirects = false
            connection.useCaches = false
            connection.connectTimeout = 15000; connection.readTimeout = 90000
            connection.requestMethod = method
            connection.setRequestProperty("Accept", "application/json")
            val cookie = session.cookie
            if (cookie.isNotEmpty()) connection.setRequestProperty("Cookie", cookie)
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val bytes = stream?.use {
                val output = ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                while (true) {
                    val count = it.read(buffer)
                    if (count < 0) break
                    require(output.size() + count <= 24 * 1024 * 1024) { "Respuesta demasiado grande" }
                    output.write(buffer, 0, count)
                }
                output.toByteArray()
            } ?: byteArrayOf()
            require(bytes.size <= 24 * 1024 * 1024) { "Respuesta demasiado grande" }
            val payload = runCatching { JSONObject(bytes.toString(Charsets.UTF_8)) }.getOrElse {
                if (code in 200..299) throw IOException("El servidor respondió JSON incompleto o inválido.")
                JSONObject()
            }
            if (code !in 200..299) throw ApiFailure(code, ((payload.opt("detail") as? String) ?: "El servidor rechazó la solicitud ($code)").take(320))
            // Never retain foreign cookies or follow redirects to another origin.
            connection.headerFields.filterKeys { it?.equals("Set-Cookie", true) == true }.values.flatten().firstOrNull { it.startsWith("tqt_sesion=") }?.let {
                store.installCookie(session, it.substringBefore(';'))
            }
            payload
        } finally { connection.disconnect() }
    }
    suspend fun login(server: String, email: String, password: String): JSONObject = loginLock.withLock {
        val origin = validatedOrigin(server)
        val attempt = store.beginLogin(origin)
        try {
            request("/api/auth/login", JSONObject().put("email", email).put("password", password), session = attempt)
            val authenticated = store.session()
            if (!store.matches(attempt) || authenticated.generation != attempt.generation || authenticated.origin != attempt.origin) throw SessionChangedException()
            val user = request("/api/auth/yo", session = authenticated)
            store.finishLogin(attempt, user.getString("email"))
            user
        } catch (error: Exception) { store.abortLogin(attempt); throw error }
    }
}
