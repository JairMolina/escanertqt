# Memoria de TQT-Web

Aplicación Inventario TQT (JairMolina/escanertqt): FastAPI, SQLite, WebSockets y HTML/JS. Mantener separada de TQT-OrangePi, que contiene infraestructura del servidor.

## Android: inventario y QR comprobados — 2026-10-19

TQT0.2.0 instalada en teléfono real Android13, con sesión conservada. Rama
`codex/android-inventario-qr-20261019`, sucesora de b81eeb2. Causa confirmada del
Not Found: producción devuelve404 a `/api/android/devices`; los GET existentes
`/api/pcb`, `/api/pcb/{id}`, `/api/esp32/r2/status` y `/api/esp32/firmwares` sí
sirven el mismo inventario. La app ahora usa esos contratos para consultar sin
desplegar cambios en producción. Búsqueda11→0011, QR local/cámara, filtros
Todas/R1/R2/R3, paginación completa y ficha con firmware/estado/evidencia real.
No confundir firmware registrado con programación físicamente verificada.

40JVM correctas, lint0errores/15avisos, 10casos instrumentados distintos en el
teléfono (9iniciales+4inventario finales con3repetidos), SDK firma/metadatos,
cámara física abierta y navegación real. Se recorrieron300PCB sin duplicados;
11 y QR simulado encontraron la misma R20011 y ficha/catálogo sin error.
USB/instalación/control verificados sin intervención y ADB sin caducidad a
petición del usuario. Logs/capturas/identificadores privados fuera de Git.

Sin despliegue ni escritura de inventario. El servicio Android de programación
no está desplegado: nuevas operaciones quedan deshabilitadas con explicación;
no sustituir sus contratos por endpoints web distintos. Falta R2 física para
BLE/OTA/cortes; firma y publicación definitivas siguen pendientes. Guía:
`docs/ANDROID_INVENTARIO_020.md`. CM mediante configuración local de alcance
ya existente `privado/cm-scope` apunta al checkout Android sin cambiar el
registro global del proyecto. Conserva identidad y namespace Laptop-TQT-Web.

## Android y firmware offline — 2026-10-17

Rama de ensayo `codex/tqt-android-ota-20261017` basada en2b91f0b; producción conocida
sigue web1.4.3/11cc0585. Se prepararon Android0.1.0 (`com.tqt.ota`, Kotlin/Compose,
API26–36), API autenticada `/api/android`, outbox cifrado por operador/origen,
paquetes offline por tarjeta/imagen/teléfono y FW4.3. Reutiliza SQLite, catálogo,
credenciales por unidad, alta genérica4.0 fija y OTA4.2; no son dos inventarios.

FW4.2 y el alta de base4.0 requieren autorización online. Tras instalar4.3 online
y vincular INFO auténtico, un grant firmado408B permite sesión BLE nueva offline
con firma Keystore del teléfono. CONTROL5/state7/manifiesto472B; INFOlegacy≤512B
+ extensión READ190B UUID0006. Contrato `protocols/offline-v1.json`; guías
`docs/ANDROID_IMPLEMENTACION.md` y `android/README.md`. El contador durable se
consume antes del COMMIT y el éxito exige recibo/hash/arranque válidos; no hay
revocación UTC inmediata sin red. El firmante existente debe coincidir con la
base fija; nunca generarlo automáticamente para habilitar offline.

Pruebas reales:105backend,32JVM,7instrumentadas Android en emuladorAPI36 (login
HTTPS/catálogo/navegación/Keystore/almacenamiento), Playwright escritorio/móvil,
apksigner/aapt sobre APK debug y rechazo de release sin firma, compilación4.3
core3.3.11/app1,159,888B y harness crypto nativo+4contrato. No hubo programación
física ni despliegue. Faltan teléfono/R2, cortes/rollback/BLE reales, custodia de
firma Android y publicación aprobada. El APK debug es solo de ensayo.

CM resolvió una discrepancia importante: main/MEMORIA histórica no describían la
última rama web1.4.3. Reutilizar las versiones contrastadas, no deducir producción
de main. Comparación de recuperación delimitada:2071vs4355bytes,52.45%menos
contexto,1cachehit; no demuestra ahorro global de tokens.9MCP de CM,0Gemini nuevo,
5auxiliares reutilizados. Original del prompt en adjuntos internos fue rechazado
por `cm files add`; se conservó sin eludir esa política.

## Estado confirmado 2026-10-13

Versión 1.3.72 publicada en GitHub main y desplegada, por autorización expresa del usuario, en https://inventariotqt.site. Commit de aplicación cdad30fa90f61b5a471cff394ff42f7c1bacb047. Integra Test Station 0.6.3 en validacion y catálogo HEX, selección de firmware y cancelación STM32 en programacion. Se conserva Docker local de esta laptop, puerto loopback 18080 y volumen independiente con copia íntegra del inventario: 100 tarjetas y 300 PCB. Agente Windows saliente para COM/BLE; cinco módulos originales idénticos en SHA256, tiempos y 14 etapas conservados.

Dos pruebas físicas R1 0036 / COM10 / R2 0077 finalizaron 14/14 aprobadas, cada una con ID e historial independiente. Reportes con cotejo de inventario, JSON y LOG íntegro; las pruebas no autorizan liberar tarjetas. Datos originales de tarjetas, PCB e historial de fabricación permanecen idénticos.

## Accesos y límites

Web local http://localhost:18080/monitor#/validacion. Instrucciones y evidencias en docs/PRUEBAS_TQT_LOCAL.md. Base, respaldo, credenciales y reportes reales fuera de Git. CM preservó los originales aportados en almacenamiento privado central; no se indexan binarios ni bases.

Servidor actual: Orange Pi en 192.168.4.70, usuario orangepi, repositorio /home/orangepi/escanertqt; acceso SSH por salto MiniPc. Tailscale de Orange Pi aparece offline. La ruta antigua devsky fue sustituida durante la restauración anterior: no desplegar en ella. Respaldo previo de código y SQLite: servidor/data/respaldos/pre-tqt-1370-20261013T212830Z; integridad y SHA256 verificados. Se reinició solo escanertqt-tqt-1; no se cambió Cloudflare ni Compose del servidor.

Agente de producción instalado en %LOCALAPPDATA%/TQT/TestStationAgent/10bdf456ab4857f132646b40, reutiliza la estación autorizada Laptop TQT · developer4. Credencial privada fuera de Git; inicio automático con pythonw oculto. COM y BLE desconectados al cerrar el despliegue, sin ejecutar nuevos movimientos. Las dos pruebas de desarrollo permanecen en la copia local; no se importaron como pruebas de producción.

Hay deuda de regresión preexistente en pruebas Linux; la comparación con GitHub no encontró fallos nuevos. Consulte docs/DESPLIEGUE_TQT_1370.md y la guía local antes de reiniciar/restaurar; revise la tarjeta físicamente antes de repetir una ejecución interrumpida.

Corrección 1.3.71: trabajo fbfa860f35229109b8d843276f6ede23 de R3 0039 cancelado en espera a petición del usuario, sin grabaciones activas. Agente de pruebas COM/BLE ya no actualiza el heartbeat de programación STM32: no confundir online de pruebas con J-Link. Estación J-Link efectiva «Lap Leo 13-10-2026» (a067f7abc49096cc65a520ce) online; agentes STM32 instalados en esta laptop actualizados. Botón «Detener y cancelar programación» y recuperación del trabajo tras recargar. Respaldo pre-tqt-1371-20261013T233704Z. Ver docs/CANCELACION_STM32.md.

Catálogo 1.3.72: tabla persistente stm32_firmwares, subida validada con confirmación HW/FW R3, selector de la versión más alta compatible y snapshot inmutable en cada trabajo. R1 usa perfil interno y personalización por inventario. Respaldo de despliegue pre-tqt-1372-20261014T002844Z. 37 casos STM32/catálogo y 11 TQT correctos; Playwright verificó formulario y selector, duplicados, reinicio Docker y móvil. V1.1 aportado se usó solamente para validación y el formulario se canceló: no está registrado localmente ni en producción, ni se programó una tarjeta. Producción conserva solamente R1 4.3 y R3 1.0 al cierre; el usuario puede subir sus HEX después. Ver docs/CATALOGO_FIRMWARE_STM32.md.
