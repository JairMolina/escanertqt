# TQT Android 0.1.0

Aplicación nativa privada `com.tqt.ota`: Kotlin, Compose/Material3, Android8/API26
mínimo, target/compile36. No usa Google Play Services. Pertenece a este repositorio;
SQLite del servidor sigue siendo el inventario único. La base local solo conserva
permisos y evidencias cifrados, separados por origen HTTPS y operador.

## Construir y probar

JDK21 (se usó el JBR de Android Studio), SDK36, Gradle9.4.1 y AGP9.2.0. Configurar
`local.properties` con `sdk.dir` local; no versionarlo. Las versiones están fijadas
en los archivos Gradle. El wrapper proviene de la distribución Gradle, Apache2.0.

```powershell
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
.\gradlew.bat :app:assembleDebug :app:assembleDebugAndroidTest :app:testDebugUnitTest :app:lintDebug
```

Instalar el APK debug únicamente para ensayos. `assembleRelease` produce un APK
**sin firma** mientras no estén presentes las cuatro variables siguientes:

`TQT_ANDROID_KEYSTORE`, `TQT_ANDROID_STORE_PASSWORD`, `TQT_ANDROID_KEY_ALIAS`,
`TQT_ANDROID_KEY_PASSWORD`. El keystore debe permanecer fuera del repositorio,
con custodia y respaldo propios. No se creó una identidad definitiva de firma.
Un debug APK no se convierte en publicación aprobada por compilar correctamente.

## Operación

1. Iniciar sesión con servidor HTTPS y cuenta habitual; seleccionar R2/firmware.
2. Permitir Bluetooth cercano (Android12+) o ubicación (Android8–11), buscar y
   seleccionar la unidad física. Revisar el diálogo antes de iniciar.
3. FW4.2 reutiliza la autorización online existente. La base genérica4.0 mantiene
   alta online; los equipos sin OTA requieren su procedimiento USB vigente.
4. FW4.3: instalar primero online y vincular su identidad real. «Autorizar y guardar
   paquete offline» descarga un permiso para esa tarjeta, imagen y teléfono.
   Después se selecciona en Tarjetas y puede iniciar una nueva sesión sin Internet.
5. Historial permite verificar sin reinstalar y sincronizar evidencias. Tras un
   COMMIT incierto no se repite automáticamente la transferencia. Un permiso no
   consumido puede recuperarse mediante INFO firmado y reintentarse explícitamente.

Las ventanas de vigencia son política de app/servidor; el equipo carece de reloj
UTC fiable y no admite revocación instantánea offline. No borrar datos de la app:
se perderían las claves Keystore y los permisos/evidencias aún no sincronizados.

Pruebas instrumentadas: `PrivateStoreInstrumentedTest` y la prueba Keystore no
necesitan servidor. La prueba UI HTTPS exige emulador y argumento explícito
`fixtureCertificate`, correspondiente solo al servidor sintético local de ensayo.
El certificado se acepta exclusivamente dentro de ese proceso de test; el cliente
de producción mantiene TLS y validación de nombre normales.

Detalles de API, despliegue pendiente y evidencia: `docs/ANDROID_IMPLEMENTACION.md`.
