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

## Prueba física completada el 15 de octubre de 2026

Tras LISTO del usuario en COM3/BOOT, esptool confirmó primero la MAC de silicio
8C:8C:29:C3:D6:A4. Se grabaron1.201.136 bytes a460.800 baudios en17.3 segundos
y se verificó el hash de Flash. Se avisó inmediatamente para liberar BOOT y
reiniciar. El usuario confirmó reinicio/alimentación normal y Bluetooth libre.
La herramienta autenticó INFO real antes de iniciar la actualización local.

OTA completa 4.1.1→4.1.1 mediante cliente local Bleak, sin usar la web:

| Medición física | Resultado |
|---|---|
| Aplicación enviada | 1.135.600 bytes |
| MTU negociado / datos por paquete | 517 / 500 bytes |
| Tiempo de transferencia, incluida validación antes de READY | 71.758 s |
| Velocidad media | 15.45 KiB/s |
| Confirmaciones recibidas por notificación | 951 |
| Partición anterior / nuevo arranque | 0x10000 / 0x150000 |
| Hash esperado y confirmado tras reiniciar | 2e21a2723f1ee914c0e876978a13a125ee52d1adbb70df2b9855504d0660b465 |

Se validaron versión, prueba HMAC de INFO, hash exacto, nonce nuevo y partición
distinta después del reinicio. Resultado `verified=true` en
`outputs/r2_ble_probe/ota_fast_result.json`. Enlace desconectado al finalizar,
sin movimientos de relés ni cambios/despliegues en la web.

Los71.758s corresponden al envío y validación receptora; preparación, conexión
y verificación del reinicio son adicionales. Los14min de la web anterior eran
una estimación de un envío cancelado, no una medición completa. El resultado
local no demuestra todavía el tiempo de una futura implementación en Chrome.

Estado físico final: R2 0069 conserva la copia temporal4.1.1 para continuar la
integración sin otra grabación serial. Catálogo e inventario de producción no
se modificaron por esta prueba; allí sigue el registro4.1 previo. Los originales
4.1 y Freki están intactos. La opción --restore existe, pero NO se ejecutó ni
se afirma verificada. Pendiente decidir integración definitiva o restauración;
no cambiar la web hasta que el usuario solicite continuar con esa integración.

Capacidades: ECC HW/FW para trazabilidad, C++ para SDK/cola y verificación para
compilación nativa/cifrado/medición; CM para checkpoint y memoria del proyecto.
