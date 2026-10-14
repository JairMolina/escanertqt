# R2 FW 4.0 / HW 3.0

Basado en el archivo V3.1.2 aportado el 14 de octubre de 2026. Mantiene GPIO,
UUID, PPON/POFF, pulsos de relés, watchdog, UART, EEPROM y corrección eFuse.
Objetivo exclusivo: ESP32-WROOM-32E-N4. Conserva la programación irreversible
VDD_SDIO=3.3 V que ya tenía el original; no usar en otro módulo.

El perfil `tqt_profile.h` identifica HW 3.0, FW 4.0 y una plantilla de nombre
`TQT_R2_V30_0000`. La web modifica únicamente ese campo para cada R2, y
recalcula checksum y SHA256 de la aplicación. No requiere recompilar por unidad.
No se debe programar directamente la plantilla 0000 en producción.

En Programación > R2, usa **Subir BIN / HEX**, confirma el perfil y guarda.
Elige la R2 del inventario y el firmware. Por defecto se usa la versión numérica
más alta compatible con el HW de la placa. La web prepara la imagen completa,
la graba por USB serial y lee `INFO` para comparar nombre/HW/FW/MAC.

## Generar archivos

Arduino IDE: placa **DOIT ESP32 DEVKIT V1**, core **esp32:esp32 3.3.12**,
configuración y particiones por defecto, Flash 4 MB. Abre el .ino que coincide
con el nombre de esta carpeta. Ejecuta `compilar.ps1` desde PowerShell para
compilar y exportar BIN completo y HEX en `build`.

Para la web utiliza `*.ino.merged.bin` o el HEX generado por el script. El
`*.ino.bin` contiene solo la aplicación y se rechaza porque falta bootloader
y tabla de particiones. El HEX de ESP32 usa offsets de Flash desde 0x0;
un HEX de STM32 (direcciones 0x08000000) no es compatible.

El firmware añade `INFO` por USB y UART2:
`TQT_INFO {"nombre":"TQT_R2_V30_0036","hw":"3.0","fw":"4.0","mac":"..."}`.
Se conserva el comando `MAC` anterior. La copia EEPROM sigue subordinada
al nombre del firmware, por lo que una programación nueva actualiza el nombre.

Para una futura versión se cambia HW/FW una sola vez en el perfil y se compila.
El operador ya no modifica nombre, HW o FW por tarjeta. Compilación verificada;
la validación en una placa física sigue pendiente.
