# Prueba aislada de transporte BLE rápido para R2 0069

El usuario pidió detener las OTA lentas y revisar como referencia el proyecto
Freki Interfaz1.3.11/HW2.1. Después autorizó una prueba aislada en R2 0069,
alimentada normalmente, antes de modificar la web. No se despliega esta prueba.
Web de producción permanece1.3.78 y los dos jobs OTA anteriores están cancelados.

Freki permite WRITE_NR, notificaciones y MTU517; su bloque OTA lógico de2048
bytes se fragmenta, no equivale a un único paquete ATT. TQT4.1 solo ofrece
WRITE para datos y READ para estado. Se conservan autenticación, cifrado y
validación de imagen de TQT; no se copian GPIO/configuración privada de Freki.

Medición física de transporte TQT4.1 con Bleak2.1.1 de la estación existente:
identidad HMAC verificada, MAC8C:8C:29:C3:D6:A6, MTU247, payload180 bytes.
24 muestras: escritura media81.21ms, mediana117.78ms; lectura media90.01ms.
Rendimiento de escritura2.16KiB/s y estimación de transporte581s para la
aplicación, sin incluir cifrado/Flash/reinicio. El perfil/partición no cambiaron.
Se limpió con CANCEL el error disconnected de la sesión ya cancelada y se
enviaron datos solo en IDLE, donde el firmware los descarta. Sin BEGIN/COMMIT,
sin movimientos de relé ni escritura de Flash. El enlace quedó desconectado.

Copia temporal: `outputs/r2_ble_probe/TQT_R2_BLE_PROBE`, fuera del código de
producción. Se identifica como4.1.1, preserva nombre/clave por unidad y añade
WRITE_NR, MTU máximo517, paquetes de hasta500 bytes limitados por MTU y cola8.
Estado leído conserva JSON; notificaciones binarias de10 bytes confirman
estado/offset/tamaño/error. La confirmación sale tras8 paquetes procesados,
50ms de avance o cambio de estado. Flujo normal de relés y controles intacto.

Compilación nativa Arduino core3.3.12 verificada:1.135.459 bytes(86%) y
42.220 bytes RAM(12%). La imagen privada personalizada tiene1.201.136 bytes,
SHA256 e1d451cfbd51320e22e335cdc00f0033ce1aff234a4e3a1d98deb3425db4a771.
Se guarda en AppData Local TQT/programming/R2_0069_FW41, fuera de Git/Drive.
Esptool valida checksum/hash de la aplicación compilada. Prueba Docker sin red
verifica perfil, identidad, HMAC de manifiesto138 bytes y AES-CTR fragmentado,
reconstruyendo exactamente la aplicación objetivo. Sintaxis de Python correcta.

Herramienta local `outputs/r2_ble_probe/run_fast_ota_probe.py`: autentica INFO,
autoriza manifiesto con nonce leído después de CANCEL, envía ventanas de ocho
sin respuesta, espera notificaciones con offset, activa solo en READY y verifica
tras reiniciar hash, versión, nonce y cambio de partición. No usa el catálogo
ni la API de producción. Opción --restore prepara la imagen4.1 original para
restaurarla después desde el firmware de prueba. Ante activación incierta queda
seguimiento privado; no se declara éxito sin nueva INFO auténtica.

Pendiente: usuario debe conectar USB–TTL COM3 y confirmar LISTO/BOOT+RESET solo
al estar todo preparado. Hasta este punto la copia4.1.1 NO se grabó. Comprobar
MAC de silicio8C:8C:29:C3:D6:A4 antes de escribir; avisar al terminar para
liberar BOOT/reiniciar y retirar contactos tras INFO. Medir OTA completa y
restauración antes de proponer cambios de firmware/web definitivos.

Capacidades: ECC HW/FW para trazabilidad, C++ para SDK/cola y verificación para
compilación nativa/cifrado/medición; CM para checkpoint y memoria del proyecto.
