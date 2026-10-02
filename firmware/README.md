# Firmware ESP32 (R1 y R2)

Copia versionada de los `.ino` que se flashean a las placas R1 (`esp32_r1/ESP32_BLE_SERIAL`) y R2
(`esp32_r2/TQT2_RESPALDO_V2_1_CORREGIDO`). Los originales de referencia (y el proyecto STM32 de R1
"Principal", que **no** se toca desde la app) siguen en
`Desktop\Todos los FW de las TQT Corregidos`.

La app los compila on-demand dentro del contenedor Docker (`app/services/firmware_build.py`, endpoint
`POST /api/firmware/compilar`) con `arduino-cli` y la placa `esp32:esp32:esp32doit-devkit-v1` (DOIT ESP32
DEVKIT V1), y el navegador los flashea por USB con Web Serial (sección "MAC y firmware" de la consola de
escritorio, `/monitor`). El binario que se flashea es el `*.ino.merged.bin` (bootloader + particiones + app
en un solo archivo, offset `0x0`).

**R2**: al compilar se sustituye únicamente el grupo final de 4 dígitos del
`#define Nombre_Del_Ble "TQT_R2_V2_0_0049"` por el número de la tarjeta (todo lo demás del archivo se
compila tal cual). **R1** no lleva número en el código (usa un nombre por defecto en EEPROM); se compila
sin ningún parche.

## Actualizar una versión de firmware

1. Reemplaza el `.ino` correspondiente aquí mismo, conservando el nombre de archivo y de carpeta
   (deben coincidir: es una regla de Arduino). Para R2, conserva la forma exacta del
   `#define Nombre_Del_Ble "TQT_R2_V2_0_XXXX"` (prefijo + 4 dígitos finales) o el parcheo automático
   fallará con un error claro en vez de compilar algo incorrecto.
2. Reconstruye la imagen Docker (`docker compose up -d --build`) para que quede horneada.
3. Prueba flashear una tarjeta de prueba antes de usarlo en planta.
