# R2 FW 4.1 / HW 3.0: instalación serial y actualización Bluetooth

Basado en R2 V4.0. Objetivo: ESP32-WROOM-32E-N4, Flash 4 MB, Arduino ESP32
3.3.12, placa DOIT ESP32 DEVKIT V1 y particiones por defecto. Conserva GPIO,
UUID de control, PPON/POFF, relés, UART, EEPROM, watchdog y corrección eFuse
VDD_SDIO=3.3 V del original. Esa corrección es irreversible; no usar otro módulo.

El perfil de 128 bytes declara FW 4.1, HW 3.0, nombre plantilla 0000,
capacidad OTA y credencial vacía. **No grabar directamente esta plantilla**.
En Programación > R2, la web prepara el nombre real y una credencial privada
por unidad durante la primera instalación serial. Se verifican INFO,
nombre/HW/FW/MAC y el identificador de credencial antes de guardar el resultado.

## Compilar y subir

Abre el .ino que coincide con su carpeta o ejecuta `compilar.ps1` en PowerShell.
El script genera en `build` el BIN completo `*.ino.merged.bin` y un Intel HEX.
Sube **merged.bin** o ese **HEX completo** a la web; no subas `*.ino.bin`
(aplicación sola). Para nuevas versiones cambia FW una vez en `tqt_profile.h`.
Mantén esquema 2, capacidad 1, servicio OTA y particiones compatibles.

## Actualizar por Bluetooth

Después de instalar por serial y registrar una R2 V4.1+, elige esa R2 y un
firmware OTA del catálogo. «Actualizar por Bluetooth» conecta la placa por
nombre, verifica identidad y recibe del servidor la aplicación cifrada.
Requiere Chrome/Edge, Bluetooth y HTTPS o localhost. Mantén alimentación estable
y libera la conexión Bluetooth con la R1. Durante OTA se bloquean comandos de relé.

La imagen se escribe en la partición inactiva. Se comprueban autorización,
integridad, perfil y credencial antes de activar y reiniciar. El arranque nuevo
confirma Bluetooth, cola de relés y watchdog; si falla, usa el rollback del SDK.
La web guarda el resultado solo después de verificar la imagen instalada y el
cambio de partición con una prueba autenticada del dispositivo.

«Detener actualización Bluetooth» cancela antes de activar. Si se corta la
conexión después de activar, usa «Verificar OTA pendiente»; no repitas serial.
«Descartar pendiente» elimina el seguimiento y no revierte el firmware grabado.
Si no arranca o se pierde la credencial, recupera por serial desde la misma web.

La SQLite persistente guarda catálogo y credenciales por unidad: conserva sus
respaldos privados. No publiques imágenes personalizadas ni credenciales.
La autenticación OTA no sustituye Secure Boot ni cifrado de Flash.
Compilación y pruebas automáticas verificadas; validación física en R2 0069
pendiente hasta que el usuario indique conexión lista en COM3.
