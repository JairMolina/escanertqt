# R2 V4.1: OTA Bluetooth y web 1.3.77

La primera instalación sigue por serial y prepara nombre desde inventario,
HW/FW desde el archivo y credencial aleatoria de 32 bytes por PCB. El perfil
esquema 2 conserva el marcador anterior y añade capacidades y credencial;
una carga al catálogo normaliza nombre 0000 y clave cero. El firmware base
no contiene secretos. R2 V4.0 sigue disponible para instalación serial.

Se añade un servicio BLE independiente `d45a0001-6a76-4e41-9f38-a7043f0ec069`
con INFO, control, datos y estado (sufijos 0002–0005). Conserva los UUID y
comandos PPON/POFF anteriores. No se procesan movimientos durante OTA.
El navegador elige por nombre; el servicio se descubre como optionalServices.
Cada paquete usa offset LE de 4 bytes y hasta 180 bytes de contenido, reducido
según MTU. La cola de ocho paquetes se vacía desde loop, fuera del callback BLE.

INFO firma nonce fresco, SHA de aplicación, identidad, MAC, arranque válido y
partición. El servidor comprueba HMAC-SHA256 con la clave privada de la unidad.
El manifiesto de 138 bytes firma nonce, SHA del archivo, tamaño, nombre, HW,
FW y MAC. La aplicación se cifra con AES-256-CTR, clave derivada por HMAC de
la clave de unidad y nonce. La API no devuelve la clave privada al navegador.
Los permisos de programación y CSRF se aplican a preparación/resultado/cancelación.

El ESP32 escribe la partición inactiva, verifica checksum/SHA del SDK, hash de
transferencia y perfil completo (incluida clave), y activa solo al recibir COMMIT.
Cancelación, desconexión o timeout abortan sin sustituir la aplicación activa.
El SDK compilado activa rollback; `verifyRollbackLater` impide la confirmación
anticipada de Arduino. Después de tres segundos se confirman salud de arranque,
hash, cola, watchdog y controlador Bluetooth. Una falla conserva la recuperación
por serial; estas comprobaciones no certifican eléctricamente el hardware.

La web registra resultados solo con prueba auténtica de nueva imagen,
versión exacta, nonce nuevo y partición diferente. Esto permite comprobar
una reinstalación de la misma versión sin confundirla con el firmware anterior.
Un resultado perdido tras reinicio queda en sessionStorage para verificarlo
sin volver a grabar. Descartarlo cancela su registro, no revierte la placa.
El seguimiento vence en una hora y pertenece al operador que lo inició.

Persistencia: `esp32_firmwares`, `esp32_unit_keys` y `esp32_ota_jobs` en la
SQLite existente. El respaldo íntegro debe conservar las credenciales privadas
además del catálogo. No guardar imágenes personalizadas, DB ni secretos en Git.
La protección del transporte BLE no sustituye Secure Boot o cifrado de Flash.

Compilación nativa Arduino ESP32 3.3.12 / ESP-IDF 5.5.5: 1.130.943 bytes (86%)
y 42.196 bytes RAM (12%). BIN completo normalizado: 1.196.624 bytes, SHA256
`3b1c3a42e51b99cc91bf770780d287f5c6604787d83eee9dced8224e97c9d08a`.
Esptool 5.3.1 valida checksum/hash de aplicación. Fuente V4.0 y original intactos.
HEX exportado validado registro por registro y reconstruido idéntico al BIN.
Pruebas Docker sin red: 28 ESP32/OTA, 37 STM32 y 13 de programación por lote,
78 correctas. `node --check` en ambos JS modificados y `git diff --check` correctos.
Proyecto independiente con BIN/HEX y script de compilación en la carpeta
`ESP32_BLE_SERIAL/TQT_R2_V4_1_14_10_2026`, conservando V3.1 y V4.0.

Playwright en contexto nuevo aislado y DB sintética: envío de 6.285 paquetes,
resultado verificado, pérdida simulada del resultado seguida de recuperación
sin nueva grabación, y cancelación antes de activar. DB de prueba: dos jobs
verificados y uno cancelado. OTA deshabilitada al seleccionar V4.0. Sin desborde
horizontal en escritorio de 1.366 px y móvil de 390 px. Ningún mock permanece
en el contexto que se utilizará para hardware.

Pendiente: publicar la web 1.3.77 con autorización expresa de despliegue y
validar físicamente R2 0069, adaptador COM3 indicado por el usuario. No se ha
abierto COM3 ni grabado ninguna placa en este avance. Avisar justo antes de
la prueba porque el usuario sostiene los contactos de programación.

Capacidades utilizadas: CM continuidad/checkpoint/Git/memoria; ECC HW/FW y
C++ para protocolo y restricciones del SDK, seguridad para identidad/credencial
y autorización, verificación para compilación, pruebas y revisión del diff.
