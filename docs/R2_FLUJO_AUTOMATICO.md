# R2 automática · web 1.3.81

## Hallazgo y versiones

FW 4.1 ya recibía imágenes OTA completas cifradas, validaba HMAC, SHA-256 y perfil, grababa la partición inactiva, activaba y confirmaba el arranque. Su transporte era lento (escritura con respuesta, hasta 180 bytes y consultas JSON). FW 4.1.1 incorpora MTU 517, 500 bytes útiles, Write Without Response y notificaciones con ventana de ocho paquetes. La web mantiene ambos transportes y reutiliza dispositivos previamente autorizados cuando el navegador los ofrece.

Se incorpora `TQT_R2_BASE_V4_0_OTA` (schema2) sin reemplazar `TQT_R2_V4_0` (schema1, sin OTA). La versión 4.0 sola no demuestra OTA: se requiere la credencial por unidad y la respuesta autenticada del dispositivo. El catálogo conserva ambos hashes/IDs; 4.1.1 sigue siendo la versión vigente. El firmware 4.1.1 existente es compatible con la base nueva y no necesita cambiar su código.

Corrección1.3.82: borrar FW/MAC en inventario no deshabilita el intento BLE si existe la credencial. Un FW registrado anterior a4.0 pide USB. Cuando FW está vacío o es4.0+, el dispositivo decide mediante protocolo, HMAC, identidad y arranque reales antes de transmitir. Si falta MAC en inventario, se usa provisionalmente la MAC autenticada, comprobando unicidad; solo se persiste después del nuevo arranque verificado. El 4.0 original sin OTA no se autoriza por su número. Habilitar el botón no cambia el estado Sin programar.

Base compilada con Arduino ESP32 3.3.12, DOIT ESP32 DevKit V1, GCC 14.2.0 / 2511. Programa 1.135.459 bytes (86%), RAM 42.220 (12%). Flash 4 MB: app0 0x10000 y app1 0x150000, 0x140000 cada una. El SDK instalado define CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=1. La confirmación temprana de Arduino se difiere para comprobar el arranque. No se afirman ensayos físicos de rollback o pérdida de alimentación.

Plantilla normalizada base4.0: SHA256 `c813c38e0d15dd94cad46880801a6502ecf96bd6458e071a22c8d7fa86c501ec`. Nombre 0000 y clave vacía; los binarios personalizados y tokens se guardan fuera del repositorio.

## Flujo

1. La sección abre TQT R2. Lista y detalle comparan firmware instalado validado con el catálogo compatible con su HW. Un registro de texto sin evidencia no se pinta como programación validada.
2. Tarjeta nueva o incompatible: instalar base4.0 OTA por USB. Se leen nombre/MAC/HW/FW/key_id por serial. Un único agente local coincidente o la estación previamente elegida se reserva antes de escribir.
3. El agente busca por MAC exacta, comprueba el nombre anunciado cuando está disponible, lee INFO por el UUID OTA y se desconecta. No usa PPON/POFF ni escribe en GATT.
4. El servidor contrasta credencial/HMAC, nombre, HW, MAC observada/reportada, versión, arranque y hash exacto de la imagen personalizada. Rechaza resultados ajenos, vencidos, repetidos o cancelados. Solo después guarda el éxito en el inventario.
5. La base aparece desactualizada frente a 4.1.1. Actualizar por Bluetooth conserva la identidad y confirma hash, nonce nuevo y partición distinta tras reiniciar. Guarda método Bluetooth OTA.
6. Las unidades ya compatibles se verifican al seleccionarlas mediante el agente. La comprobación de solo lectura cambia verified_at y conserva programmed_at. Se ofrece continuar con R1 y después R3; las pestañas siguen disponibles manualmente.

Web Bluetooth requiere permiso del navegador para un dispositivo nuevo. El agente saliente evita un segundo selector durante la verificación; no abre puertos locales ni recibe claves de unidad. El servidor mantiene las claves. El agente anterior debe actualizarse antes de usar la verificación nueva. El instalador existente ya empaqueta el nuevo agent.py; no se cambian credenciales ni registro de estación.

Velocidad predeterminada: 460800, sincronización ROM115200. La preferencia anterior de 921600 no se reutiliza silenciosamente; el override nuevo vive en Mantenimiento. Hay un único reintento automático a115200. Con contactos manuales todavía se requieren BOOT/RESET y reinicio físico; no se presupone cableado de reset automático.

## Datos y concurrencia

- `r2_programming_attempts`: intentos persistentes, PCB/firmware/operador/estación/método, snapshot esperado, estado, resultado/error y tiempos. Transiciones flashing → queued → running → verified/error; vencimiento600s. Los resultados de un trabajo cancelado o vencido se rechazan.
- `r2_programming_state`: una fila por PCB con método, fecha de instalación, fecha de verificación, HW/FW, hash y tipo de evidencia. Fecha desconocida histórica se mantiene como desconocida; no se inventa una fecha de grabación.
- `r2_agent_presence`: capacidad del agente, disponibilidad y heartbeat. El agente usa el mismo hilo BLE que la validación, evitando conexiones simultáneas de ese proceso.
- Se reutilizan `pcb_inventario`, su versión HW, unicidad de MAC y actualización de pareja. No se crean PCB nuevas al verificar. Los WebSockets notifican el resultado.
- Bloqueos entre pruebas TQT, comandos manuales, STM32, verificación R2 y OTA de la misma unidad/estación. El usuario ve un error diferenciado; un fallo no borra un éxito histórico ni convierte una versión vieja en actualizada.

## Evidencia real

Todas las pruebas usaron Docker y bases aisladas. La producción no se modificó en esta fase.

R2 0069 / ESP32-D0WD-V3 rev3.1, MAC de silicio 8C:8C:29:C3:D6:A4 y BLE 8C:8C:29:C3:D6:A6:

- Adaptador CH340 detectado en COM4 (COM3 ya no existía). Primer intento COM3 no escribió nada.
- Base4.0 por esptool a460800: 1.201.136 bytes, 745.989 comprimidos, escritura17,2s y hash leído correcto. BOOT liberado y reinicio confirmado por el usuario.
- Agente nuevo → API local → SQLite: verificación BLE2,85s, HW3.0/FW4.0, método serial y estado desactualizada.
- OTA4.0 →4.1.1 con autorización/cifrado de API local: 1.135.600 bytes, bloque500,953 notificaciones,71,698s y15,47KiB/s; partición0x10000 →0x150000. INFO/HMAC/hash/nonce/nuevo arranque verificados. Estado actualizado, método ble_ota.
- Hash esperado y confirmado: `2e21a2723f1ee914c0e876978a13a125ee52d1adbb70df2b9855504d0660b465`.
- Web local real → agente → R2 física → API → interfaz: al seleccionar0069 se verificó sin selector; cero llamadas requestDevice, sin erroresJS. No equivale a probar el envío OTA por Web Bluetooth.
- Playwright con transporte serial simulado: reducción460800→115200, un intento persistente y verificación automática posterior sin selector. Interfaz R1/R3 conservada; móvil revisado.
- Pruebas unitarias: ESP3236, STM3237, TestStation11 y R2/agente13; transporteJS7 escenarios. Nuevos casos cubren MAC/hash/HMAC incorrectos, autenticación, propiedad de trabajos, expiración, cancelación, INFO repetida y fecha de instalación.

No se probaron físicamente el fallback de velocidad, cortes de alimentación/rollback ni una grabación Web Serial completa. R2 0069 quedó finalmente en4.1.1, desconectada de BLE. Las salidas no se accionaron. Los archivos de evidencia locales viven en outputs/r2_ble_probe y no incluyen claves; el entorno físico aislado usa almacenamiento privado fuera de Git.

Referencias oficiales: [permisos Web Bluetooth](https://developer.chrome.com/docs/capabilities/bluetooth), [OTA y rollback ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/v5.5.2/esp32/api-reference/system/ota.html). El contrato efectivo se comprobó además en el SDK3.3.12 instalado y la tabla de particiones.
