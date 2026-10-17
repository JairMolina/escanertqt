# TQT Android / OTA offline — implementación de ensayo

2026-10-17. Rama `codex/tqt-android-ota-20261017`, base
`2b91f0b2c3b4f0bc8df194e2e80afddc834aa9cb`. Producción conocida conserva web1.4.3,
commit11cc0585; este trabajo no la desplegó ni grabó dispositivos.

## Existente y ampliación

Ya existían FastAPI/SQLite, sesiones/roles, catálogo versionado de firmware,
personalización por unidad, OTA BLE1, historial, estación serial y alta de la
base genérica4.0. Se reutilizan; no se crea otro inventario ni backend.

Se añade Android0.1.0, API `/api/android`, registros durables de operación/UUID,
revisión causal de inventario, permisos offline firmados, FW4.3 y página privada
`/android` accesible desde la consola. Los resultados autentican arranque real,
hash, HW, identidad, nonce nuevo y partición; transmitir todos los bytes no es
éxito. Evidencia auténtica tardía/conflictiva se conserva sin sobrescribir el
inventario actual. Una operación concurrente de web, app o estación se bloquea.

FW4.2 requiere conexión para una autorización nueva. FW4.3 añade CONTROL5,
grant408B y manifiesto de sesión472B. INFOlegacy permanece≤512B; la extensión
binaria190B tiene UUID0006 y se verifica junto al mismo snapshot legacy.
Contrato normativo: `protocols/offline-v1.json`; fuentes y harness nativo en
`firmware/esp32_r2/TQT_R2_V4_3`. Base4.0 y fuentes4.2 intactas.

El servidor firma con la clave de alta **existente**, validada contra el ancla
pública fija. Si falta o no coincide, rechaza offline; no crea/reemplaza claves.
La unidad genera una identidad P256 persistente en NVS; su HMAC original vincula
la clave pública al inventario. Android conserva su clave privada en Keystore,
nunca recibe claves de unidad ni el firmante global. El permiso limita tarjeta,
teléfono, contador/hash origen e imagen/HW/FW/nombre/MAC destino. Cada COMMIT consume
contador durable antes de cambiar el arranque. Cortes entre ambos pasos necesitan
otra autorización online; un blob NVS corrupto no se regenera silenciosamente.

App/servidor aplican vigencia24h; ventana prevista de recepción7d. Una evidencia
auténtica posterior se conserva como histórica. No hay vencimiento UTC fiable
ni revocación inmediata dentro del microcontrolador. No afirmar esas garantías.

## API y distribución privada

- `GET /api/android/devices`, `/{pcb_id}`, `/{pcb_id}/capability` y `/firmwares`.
- `POST /operations/prepare`, `GET /operations[/{UUID}]`, `POST /operations/{UUID}/result`.
- `POST /offline/bind/{pcb_id}`, `POST /offline/packages`, `GET /offline/packages[/{UUID}]`.
- `POST /offline/operations/{UUID}/result`: before/after firmados, firma de sesión y resultado.
- `GET /apk/manifest` y `/apk/download`: sesión requerida;503 mientras no haya publicación aprobada.

Todas las rutas anteriores comparten prefijo `/api/android`. Solo el operador
original puede recuperar/reportar sus permisos. Consultor conserva acceso de
lectura; el servidor impide autorizaciones de escritura. No hay conexión SQL
desde Android ni acceso Docker desde la aplicación.

Para publicar posteriormente, proporcionar keystore estable fuera de Git,
construir release firmado y custodiar su respaldo. Configurar fuera del checkout
`TQT_ANDROID_APK_DIR` con APK y `manifest.json`, y rutas absolutas SDK
`TQT_ANDROID_APKSIGNER`/`TQT_ANDROID_AAPT` en el contenedor. Manifest requiere
`approved:true`, `filename`, `package_name`, `version_code`, `version_name`,
`min_sdk`, `sha256`, `certificate_sha256`. El servidor verifica ZIP, hash,
firma/certificado y metadatos reales; no basta cambiar `approved`. Conservar las
publicaciones anteriores fuera de Git bajo la política de respaldo correspondiente.
La página muestra versión e integridad; Android avisa si el manifest tiene mayor
version_code. La emisión definitiva, fecha/notas e historial de publicaciones
quedan ligados al proceso de firma/aprobación pendiente; no hay APK productiva.

Antes de migrar producción: respaldo verificable de SQLite y archivos, ensayo
de restauración, preflight Compose/espacio y autorización de despliegue. Las
tablas nuevas/guards son aditivas y transaccionales, probadas en BD sintéticas;
no se aplicaron sobre la BD real. Para revertir código tras conservar evidencia,
dejar las tablas nuevas archivadas; no ejecutar DROP ni restaurar una BD vieja
encima de resultados posteriores. Mantener secretos/volúmenes/configuración.

## Verificaciones y límites

- Backend:105/105 (20offline y85 de Android online/OTA/alta previas), BD temporales.
- Android: build debug/release, lint y32 pruebas JVM (16 wire,15 crypto,1origenHTTPS).
- Almacenamiento: cinco instrumentadas reales en emuladorAPI36; cifrado,
  aislamiento, migración sin borrar originales, registros>3MB e integridad.
- Identidad Keystore estable: prueba instrumentada real.
- UI Android: login HTTPS real, catálogo sintético, navegación, sincronización y
  guardas sin selección; siete instrumentadas completas aprobadas en API36.
- Web: Playwright, sesión real contra servidor sintético Docker HTTPS,
  escritorio1440/móvil390 sin desbordamiento,503 sin firma, copia de huella
  con respuesta aprobada simulada y sin errores JavaScript. Esa simulación
  no constituye una aprobación ni prueba criptográfica de una release.
- Protocolo JS existente:16 escenarios de regresión, sin alterarlo.
- FW: harness nativo de las fuentes reales con mbedTLS; NVS/mutex y ancla de
  prueba sustituidos explícitamente. No representa BLE/flash/boot físico.
- FW4.3 compila realmente con coreESP32 3.3.11: app1,159,888B<slot1,310,720B,
  RAM43,164B. Cuatro comprobaciones de contrato y coincidencia de fuentes compiladas.
- `tests/verify_android_apk_sdk.py`: apksigner/aapt reales aceptan el APK debug de
  ensayo y rechazan la release sin firma. No se usan ni crean claves de producción.

Evidencia privada en `privado/android-testing` y `privado/fw43-build`; no se
publican logs, certificados de ensayo, bases, SDK, cachés ni binarios personalizados.
Faltan teléfono/R2: descubrimiento y pérdida de señal BLE reales, consumo,
rollback/cortes de alimentación, OTA online4.2→4.3 y una sesión4.3 nueva sin Internet.
También quedan firma/custodia Android, publicación productiva e historial real
de releases. No se certifica compatibilidad física por compilar o por el emulador.

## CM y eficiencia observada

Tres búsquedas de auditoría en TQT-Web/Laptop-TQT-Web recuperaron arquitectura,
decisiones y estado. Contrastarlas con Git detectó que main y TQT-Web estaban
atrasados frente a la rama de producción: evitó recrear OTA y alta ya existentes.
No se exportó memoria a Gemini. Se aplicaron ECC Android/backend/security/HW-FW,
verificación/E2E y diseño pertinente; CM conserva Git, memoria y despliegue.

Comparación delimitada sobre el mismo índice vivo: consulta «Android actualización
offline», ámbito Laptop-TQT-Web. Auto recuperó2071bytes (~691tokens por bytes/3)
y full4355 (~1452). Reducción de contexto52.45%; full es contrato compatible1.0,
no una reinstalación de1.0. Auto conservó referencia actual1.4.3 que full no mostró;
no se afirma equivalencia de actualidad ni ahorro global de facturación.

Se hicieron9 llamadas MCP de CM:3 búsquedas de auditoría,4 de comparación/ref/full,
2 mediciones de uso. La repetición fue idéntica con1cachehit;1ranking,1embedding y
1ampliación de sección. Gemini:0 solicitudes nuevas. Cinco auxiliares únicos:
auditoría backend/firmware, implementación backend/almacenamiento, BLE/crypto y
FW4.3; los mismos se reutilizaron para revisión. Tokens Codex facturados/cacheados
y tiempo total de esta tarea no están aislados de este chat prolongado; no
reportar acumulados históricos como consumo de Android. Dos primeras cargas de
auditoría no midieron bytes. Las correcciones/reintentos reales constan en logs;
no se inventa un contador global de errores.

El original aportado en `.codex/attachments` permanece allí: `cm files add`
lo rechazó por su política de archivos internos. No se copió para eludirla.
El checkpoint y la sincronización curada son independientes del respaldo original.
